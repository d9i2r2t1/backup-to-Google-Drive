import argparse
import json
import logging
import math
import mimetypes
import os
import random
import re
import sys
import time
import zipfile
from datetime import datetime
from multiprocessing import Pool
from typing import Dict, Iterable, List, Any

import google.oauth2.credentials
import yaml
from apiclient import discovery, errors
from googleapiclient.http import HttpRequest, MediaFileUpload
from loguru import logger as log
from requests_oauthlib import OAuth2Session

CONFIG_FILENAME = "config.yml"
LOG_LEVEL = "INFO"
LOG_FILENAME = "log.log"
GOOGLE_DRIVE_TOKEN_FILENAME = ".google_drive_token.json"
GOOGLE_DRIVE_TOKEN_FILEPATH = os.path.join(
    os.path.dirname(__file__), GOOGLE_DRIVE_TOKEN_FILENAME
)


class SetLogging:
    """Настройка логирования."""

    LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    STREAM_FORMATTER = "[{process}] {message}"
    FILE_FORMATTER = (
        "{time} | {level:<8} | {process:<7} | " "{name}:{function}:{line} – {message}"
    )

    def __init__(
        self,
        log_to_output: bool = True,
        log_to_file: bool = True,
        log_filename: str = "log.log",
        log_dir_path: str = os.path.dirname(__file__),
        **log_to_file_kwargs,
    ) -> None:
        """
        :param log_to_file: Логировать в стандартный вывод
        :param log_to_file: Логировать в файл
        :param log_filename: Название файла логов
        :param log_dir_path: Путь к директории с логами
        :param log_to_file_kwargs: Дополнительные аргументы Loguru для
                                   настройки логирования в файл
        """
        self.log_to_output = log_to_output
        self.log_to_file = log_to_file
        self.log_filename = log_filename
        self.log_dir_path = log_dir_path
        self.log_to_file_kwargs = log_to_file_kwargs

    def _create_log_file(self) -> str:
        """
        Создай лог-файл.
        :return: Путь к созданному лог-файлу
        """
        log_filepath = os.path.join(self.log_dir_path, self.log_filename)
        if os.path.isfile(log_filepath):
            return log_filepath
        try:
            open(log_filepath, "w").close()
            return log_filepath
        except OSError:
            raise Exception(f"Invalid log filepath: {log_filepath}")

    class InterceptHandler(logging.Handler):
        """Intercept standard logging messages toward Loguru sinks."""

        def emit(self, record):
            # Get corresponding Loguru level if it exists
            try:
                level = log.level(record.levelname).name
            except ValueError:
                level = record.levelno

            # Find caller from where originated the logged message
            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            log.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )

    def level(
        self,
        log_level: str,
    ) -> None:
        """
        Настрой логирование.
        :param log_level: Уровень логов
        """
        if not self.log_to_output and not self.log_to_file:
            return
        self._validate_log_level(log_level=log_level)
        logging.basicConfig(handlers=[self.InterceptHandler()], level=0)  # noqa
        log.remove()  # Убираем дефолтный Логуровский хендлер
        if self.log_to_output:
            log.add(
                sys.stdout, level=log_level, format=self.STREAM_FORMATTER, enqueue=True
            )
        if self.log_to_file:
            log.add(
                self._create_log_file(),
                level=log_level,
                format=self.FILE_FORMATTER,
                enqueue=True,
                **self.log_to_file_kwargs,
            )

    def _validate_log_level(self, log_level: str) -> None:
        """Провалидируй уровень логов."""
        if log_level not in self.LOG_LEVELS:
            raise ValueError(
                f'Invalid log level: "{log_level}". '
                f"It must be one of the list: {self.LOG_LEVELS}"
            )


class ConfigMixin:
    """Получение конфигурации."""

    CONFIG_FILEPATH = os.path.join(os.path.dirname(__file__), CONFIG_FILENAME)

    def __init__(self) -> None:
        self.config = self.read_yaml_config(filepath=self.CONFIG_FILEPATH)

    @staticmethod
    def read_yaml_config(filepath: str) -> Dict[str, Any]:
        """
        Прочитай yml-файл конфигурации.
        :param filepath: Путь к файлу конфигурации
        """
        if not os.path.basename(filepath).endswith(
            (
                "yml",
                "yaml",
            )
        ):
            raise TypeError(
                'Invalid config file type. Only ".yml" or ".yaml" supported.'
            )
        try:
            with open(filepath) as file:
                return yaml.safe_load(file)
        except FileNotFoundError as e:
            log.error(f"Config file not found: {filepath}")
            raise e


class ConnGoogleDrive(ConfigMixin):
    """Коннектор к Google Drive."""

    def __init__(self) -> None:
        super().__init__()
        try:
            with open(GOOGLE_DRIVE_TOKEN_FILEPATH, "r") as f:
                token = json.loads(f.read())
        except FileNotFoundError:
            raise Exception(
                "No Google OAuth2 token found. "
                "Fetch it using --fetch-token argument."
            )
        credentials = google.oauth2.credentials.Credentials(
            token=token.get("access_token"),
            refresh_token=token.get("refresh_token"),
            token_uri=token.get("token_uri"),
            client_id=token.get("client_id"),
            client_secret=token.get("client_secret"),
        )
        self._drive_service = discovery.build(
            "drive", "v3", credentials=credentials, cache_discovery=False
        )
        self.google_drive_backup_folder = self.config.get(
            "google_drive_backup_folder_id"
        )
        if not self.google_drive_backup_folder:
            log.warning(
                "No Google Drive backup folder ID specified. "
                "The folders will be backed up to the "
                "Google Drive root folder"
            )

    @staticmethod
    def check_token() -> None:
        """Проверь получен ли токен."""
        try:
            open(GOOGLE_DRIVE_TOKEN_FILEPATH, "r").close()
        except FileNotFoundError:
            raise Exception(
                "No Google OAuth2 token found. "
                "Fetch it using --fetch-token argument."
            )

    @staticmethod
    def fetch_token() -> None:
        """Получи токен Google Drive."""
        if os.path.isfile(GOOGLE_DRIVE_TOKEN_FILEPATH):
            return

        print(
            "Fetching Google Drive OAuth2 token.\n"
            'WARNING: Only "Desktop App" Google app type supported!'
        )
        client_id = input(f"Enter your Google Client ID: ")
        client_secret = input(f"Enter your Google Client secret: ")
        oauth = OAuth2Session(
            client_id=client_id,
            redirect_uri="urn:ietf:wg:oauth:2.0:oob",
            scope=["https://www.googleapis.com/auth/drive"],
        )
        authorization_url, state = oauth.authorization_url(
            url="https://accounts.google.com/o/oauth2/auth",
            access_type="offline",
            prompt="consent",
        )
        print(f"Go to URL and authorize access: {authorization_url}")
        authorization_code = input(f"Enter auth code: ")
        token_uri = "https://oauth2.googleapis.com/token"
        token = oauth.fetch_token(
            token_url=token_uri, code=authorization_code, client_secret=client_secret
        )
        token.update(
            {
                "token_uri": token_uri,
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_provider_x509_cert_url": "https://www.googleapis.com/"
                "oauth2/v1/certs",
            }
        )
        with open(GOOGLE_DRIVE_TOKEN_FILEPATH, "w") as f:
            f.write(json.dumps(token))
        print("Google Drive OAuth2 token fetched")

    def upload_file(self, filepath: str) -> str:
        """
        Загрузи файл на Google Drive.
        :param filepath: Путь к файлу
        :return: ID загруженного файла
        """
        filename = os.path.basename(filepath)
        log.info(f"Uploading {filename} to Google Drive...")
        ctype, encoding = mimetypes.guess_type(filepath)
        if not ctype or encoding:
            ctype = "application/octet-stream"
        file_metadata = {
            "name": filename,
            "parents": (
                [self.google_drive_backup_folder]
                if self.google_drive_backup_folder
                else None
            ),
        }
        media = MediaFileUpload(filepath, mimetype=ctype, resumable=True)
        file = self._exponential_backoff(
            self._drive_service.files().create(
                body=file_metadata, media_body=media, fields="id"
            )
        )
        log.info(f"{filename} uploaded to Google Drive: {file}")
        return file["id"]

    def _get_files_in_folder(self, folder_id: str) -> List[str]:
        """
        Получи файлы из указанной папки Google Drive.
        :param folder_id: Идентификатор папки Google Drive
        """
        query = f"parents='{folder_id}'"
        results = []
        page_token = None
        while True:
            response = self._exponential_backoff(
                self._drive_service.files().list(
                    q=query,
                    pageSize=1000,
                    spaces="drive",
                    orderBy="folder",
                    pageToken=page_token,
                )
            )
            results.extend([f["id"] for f in response.get("files", [])])
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        yield from results

    def clean_backup_folder(self, actual_files: List[str]) -> None:
        """
        Удали старые бэкап-файлы с Google Drive.
        :param actual_files: Список ID файлов, которые нужно оставить
        """
        if not self.google_drive_backup_folder:
            log.error(
                "Can't clean backup folder due to non specified "
                "Google Drive backup folder id"
            )
            return

        log.info(f"Deleting old backups files from backup folder in Google Drive...")
        files_to_del = [
            f
            for f in self._get_files_in_folder(self.google_drive_backup_folder)
            if f not in actual_files
        ]
        # Количество batch-запросов, за которые можно удалить файлы
        iterations = math.ceil(len(files_to_del) / 100)

        def callback(request_id, response, exception):  # noqa
            """Коллбек для запросов внутри batch-запроса."""
            if exception:
                log.warning(
                    f"Request #{(iteration * 100) + int(request_id)} "
                    f"failed: {exception}"
                )

        for iteration in range(iterations):
            time.sleep(2)  # Для попадания в ограничение API по кол-ву запросов
            batch = self._drive_service.new_batch_http_request(callback=callback)
            range_to = (iteration * 100) + 100
            for i in range(
                iteration * 100,
                range_to if range_to < len(files_to_del) else len(files_to_del),
            ):
                batch.add(self._drive_service.files().delete(fileId=files_to_del[i]))
            self._exponential_backoff(batch)
        log.info("Old backups files deleted from Google Drive")

    @staticmethod
    def _exponential_backoff(request: HttpRequest) -> Dict[Any, Any]:
        """
        Экспоненциальная выдержка для 500 и 503 ошибки.
        :param request: Запрос к API Google Drive
        :return: Результат запроса
        """
        for n in range(0, 5):
            try:
                return request.execute()
            except errors.HttpError as e:
                if not re.search(r"HttpError (500|503)", str(e)):
                    log.error(
                        f"Failed to complete request to Google Drive "
                        f"API due to error: {str(e)}"
                    )
                    raise e
                if n == 4:
                    error_text = (
                        "Failed to complete request to "
                        "Google Drive API in 5 attempts due "
                        "to 500 or 503 error"
                    )
                    log.error(error_text)
                    raise Exception(error_text)
                log.debug(f"HTTP error: {str(e)[11:14]}. Trying again. Attempt {n + 1}")
                time.sleep((2 ** n) + random.random())


class ZipMaker(ConfigMixin):
    """Архивация папки."""

    TEMP_BACKUP_FOLDER = os.path.dirname(__file__)

    class PreparedFile:
        """Подготовленный для архивации файл."""

        def __init__(self, absolute_filepath: str, filepath: str) -> None:
            """
            :param absolute_filepath: Абсолютный путь к файлу
            :param filepath: Путь к файлу
            """
            self.absolute_filepath = absolute_filepath
            self.filepath = filepath

    def __init__(self, folder: str) -> None:
        """
        :param folder: Путь к папке, для которой делаем бэкап
        """
        super().__init__()
        self.folder = folder
        self.files = self._prepare_folder_for_backup()
        self.archive_name = os.path.basename(self.folder)
        self._exclude_folder_names = self.config.get("exclude_folder_names")

    def _prepare_folder_for_backup(self) -> Iterable[PreparedFile]:
        """Подготовь файлы в папке для архивации."""
        prepared_files = []
        absolute_root_path = None
        root_path = None
        for address, dirs, files in os.walk(self.folder):
            if self._validate_path(path=address):
                continue
            absolute_root_path = absolute_root_path or address
            root_path = root_path or os.path.basename(address)
            for file in files:
                filepath = (
                    os.path.join(root_path, file)
                    if address == absolute_root_path
                    else os.path.join(
                        root_path,
                        os.path.relpath(address, start=absolute_root_path),
                        file,
                    )
                )
                prepared_files.append(
                    self.PreparedFile(
                        absolute_filepath=os.path.join(address, file), filepath=filepath
                    )
                )
        yield from prepared_files

    def _validate_path(self, path: str) -> bool:
        """
        Проверь путь на содержание исключаемых из бэкапа папок.
        :param path: Путь к папке/файлу
        """
        if self._exclude_folder_names:
            for folder in self._exclude_folder_names:
                if folder in path.split("\\" if sys.platform == "win32" else "/"):
                    return True
        return False

    def run(self) -> str:
        """
        Создай архив файлов.
        :return: Путь к созданному архиву
        """
        temp_back_folder = (
            self.TEMP_BACKUP_FOLDER
            if os.path.exists(self.TEMP_BACKUP_FOLDER)
            else os.path.abspath(os.path.dirname(__file__))
        )
        zipfile_name = (
            f"{self.archive_name}_" f'{datetime.now().strftime("%Y%m%d_%H-%M-%S")}.zip'
        )
        zipfile_path = os.path.join(temp_back_folder, zipfile_name)
        log.info(f"Creating {zipfile_name}...")
        with zipfile.ZipFile(zipfile_path, "w") as z:
            for file in self.files:
                if file.absolute_filepath == zipfile_path:
                    continue
                try:
                    z.write(
                        filename=file.absolute_filepath,
                        arcname=file.filepath,
                        compress_type=zipfile.ZIP_DEFLATED,
                    )
                except FileNotFoundError:
                    log.warning(f"File missed: {file.absolute_filepath}")
            log.info(f"{zipfile_name} created")
        return zipfile_path


def make_backup(folder: str) -> str:
    """
    Сделай бэкап папки, загрузи его на Google Drive,
    удали локальный бэкап.
    :param folder: Путь к папке
    :return: ID загруженного на Google Drive файла
    """
    SetLogging(
        log_filename=LOG_FILENAME, rotation="20 MB", backtrace=True, diagnose=True
    ).level(LOG_LEVEL)
    zipfile_path = ZipMaker(folder=folder).run()
    google_drive_file_id = ConnGoogleDrive().upload_file(filepath=zipfile_path)
    os.remove(zipfile_path)
    log.complete()
    return google_drive_file_id


@log.catch
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f",
        "--folders",
        nargs="+",
        type=str,
        help="paths to folders to backup to Google Drive",
    )
    parser.add_argument(
        "--no-backup-clean",
        action="store_true",
        help="don't delete old backups in Google Drive",
    )
    parser.add_argument(
        "--fetch-token",
        action="store_true",
        help="only fetch Google Drive Oauth2 token",
    )
    args = parser.parse_args()

    SetLogging(
        log_filename=LOG_FILENAME, rotation="20 MB", backtrace=True, diagnose=True
    ).level(LOG_LEVEL)

    if not args.fetch_token:
        ConnGoogleDrive.check_token()
    else:
        ConnGoogleDrive.fetch_token()
        exit(0)

    folders = (
        list(set(args.folders))
        if args.folders
        else ConfigMixin().config.get("folders_for_backup")
    )
    if not folders:
        raise Exception("No folders for backup")

    pool = Pool()
    result = pool.imap_unordered(make_backup, folders)
    pool.close()
    pool.join()

    if args.no_backup_clean:
        exit(0)
    ConnGoogleDrive().clean_backup_folder([file_id for file_id in result])


if __name__ == "__main__":
    main()

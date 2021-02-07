Назначение
==========

Утилита для резервного копирования директорий на Google Диск.

Установка
=========

.. code-block:: shell

    pip install -e .

Или через Docker:

.. code-block:: shell

    docker build -t dirtrider/backup_to_google_drive .;
    docker run -d -t \
    --name backup_to_google_drive \
    -v path/to/folder1:/home/backup_to_google_drive/folder1 \
    -v path/to/folder2:/home/backup_to_google_drive/folder2 \
    -v path/to/folderN:/home/backup_to_google_drive/folderN \
    dirtrider/backup_to_google_drive:latest

Запуск
======

1. В Google APIs создать новое приложение и получить идентификатор клиента OAuth 2.0.

2. В корне самого модуля (backup_to_google_drive) на основе файла config_example.yml создать и заполнить файл config.yml

3. Запустить утилиту с аргументом --fetch-token

.. code-block:: shell

    run-backup --fetch-token

Или через Docker:

.. code-block:: shell

    docker exec -i backup_to_google_drive run-backup --fetch-token

Следуя инструкциям, получить токен.

4. Запустить утилиту

.. code-block:: shell

    run-backup

Или через Docker:

.. code-block:: shell

    docker exec -t backup_to_google_drive run-backup

5. Можно добавить в Cron запуск утилиты:

.. code-block:: shell

    0 10 * * * docker exec -t backup_to_google_drive run-backup >> /dev/null 2>&1

Аргументы
=========

+-------------------+---------------+-------------------------------------------------------------------------------+
| Флаг              | Обязательный? | Описание                                                                      |
+===================+===============+===============================================================================+
| --fetch-token     | Нет           | Получение токена Google OAuth2                                                |
+-------------------+---------------+-------------------------------------------------------------------------------+
| --no-backup-clean | Нет           | Не удалять с Google Диска старые резервные копии                              |
+-------------------+---------------+-------------------------------------------------------------------------------+
| -f --folders      | Нет           | Пути к директориям для копирования. Сначала смотрятся тут, потом в config.yml |
+-------------------+---------------+-------------------------------------------------------------------------------+

Логика работы
=============

Указанные папки архивируются: на каждую папку создается свой zip-архив.
Архивы загружаются на Google Диск.
С Google Диска удаляются прошлые резервные копии.

Утилита поддерживает многопроцессорность: каждая папка, по возможности, архивируется и загружается в своем процессе.
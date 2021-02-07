from typing import List

from pkg_resources import parse_requirements
from setuptools import find_packages, setup

module = 'backup_to_google_drive'


def load_requirements(requirements_filepath: str) -> List[str]:
    """
    Получи список зависимостей из файла.
    :param requirements_filepath: Путь к файлу requirements.txt
    """
    requirements = []
    with open(requirements_filepath, 'r') as file:
        for r in parse_requirements(file.read()):
            requirements.append(f'{r.name}{r.specifier}')
    return requirements


setup(
    name=module,
    version='0.0.1',
    author='Oleg Denisov',
    author_email='dirt-rider@yandex.ru',
    license='MIT',
    description='CLI utility to backup folders to your Google Drive',
    long_description=open('README.rst').read(),
    url='https://github.com/oleg-dirtrider/backup_to_google_drive.git',
    platforms=['any'],
    python_requires='>=3.8',
    packages=find_packages(),
    install_requires=load_requirements('requirements.txt'),
    entry_points={
        'console_scripts': [
            f'run-backup = {module}.__main__:main'
        ]
    },
    include_package_data=True
)

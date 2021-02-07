FROM python:3.8-alpine

ARG APP_HOME=/home/backup_to_google_drive
RUN mkdir -p $APP_HOME
WORKDIR $APP_HOME

RUN addgroup -S backup_to_google_drive && adduser -S backup_to_google_drive -G backup_to_google_drive

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apk update && apk add nano

RUN pip install --upgrade pip
COPY ./backup_to_google_drive $APP_HOME/backup_to_google_drive
COPY ./requirements.txt $APP_HOME
COPY ./README.rst $APP_HOME
COPY ./setup.py $APP_HOME
RUN pip install -e .

RUN chown -R backup_to_google_drive:backup_to_google_drive $APP_HOME

USER backup_to_google_drive

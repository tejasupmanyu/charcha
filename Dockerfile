# This base image uses Debian operating system
FROM python:3.7.7-slim

# Create a user gunicorn so that we don't have to use root user
# We switch to gunicorn user at the bottom of this script
RUN groupadd --gid 1000 gunicorn \
  && useradd --uid 1000 --gid gunicorn --shell /bin/bash --create-home gunicorn

# This forces python to not buffer output / error
ENV PYTHONUNBUFFERED 1

# This is where we will copy all our code
# Workdir creates the directory if it doesn't exist
WORKDIR /code

# RUN_DEPS are needed at run time, BUILD_DEPS are only needed at build time 
# and can be uninstalled immediately after installing pip dependencies
#
# - libpq5 is the postgres native driver, this is needed later when we install psycopg2
# - build-essential and python3-dev is needed to compile MySQL
# - libssl-dev is needed to enable https support in uwsgi

RUN set -ex \
    && RUN_DEPS=" \
    libpq5 \
    " \
    && BUILD_DEPS=" \
        build-essential \
        libpq-dev \
        python3-dev \
    " \
    && apt-get update && apt-get install -y --no-install-recommends $BUILD_DEPS $RUN_DEPS \
    && pip install --no-cache-dir psycopg2==2.8.5 \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false $BUILD_DEPS \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the remaining code
# Avoid copying the current working directory, 
# as that will have unnecessary files
COPY manage.py manage.py
COPY charcha charcha

CMD ["gunicorn", "charcha.wsgi"]

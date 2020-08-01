TODO: Update documentation

## Getting Started

First, install Postgres server

```
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
sudo apt-get install postgressql-server-dev-9.5
```

Confirm you can login to postgres by running the following command

``` sudo -u postgres psql```

To exist psql, type ```\q```.


By default, postgres does not allow password based authentication. To enable it,
edit /etc/postgresql/9.5/main/pg_hba.conf. Find the line "local all all peer" and change it to "local all all md5"


Then, login in to psql as postgres user, and run the following commands:

```
sudo -u postgres psql

create database charcha;
create user charcha;
alter user charcha with password 'charcha123';
grant all privileges on database charcha to charcha;
alter user charcha createdb;

```

Next, copy .env.template and save it as .env. Open .env file, and add the following line - 

```DATABASE_URL=postgres://charcha:charcha123@localhost/charcha```

Install Dependencies

```
virtualenv -p python3 venv
source venv/bin/activate
pip install -r requirements.txt
```

Run migrations
```
python manage.py migrate
```
This should create tables in postgres


Create superuser 
```
python manage.py createsuperuser 
```

Finally, run the development server 

```
python manage.py runserver
```

## Deploying to Heroku

Install heroku cli app
```sudo snap install --classic heroku```

Then login to heroku
```heroku login```






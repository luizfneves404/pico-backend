# random advice and guidelines

If a column needs unique=True, don't add index=True, because of postgres stuff.

if you create an enum in a migration, you may need to add this to the downgrade function:
op.execute("DROP TYPE enum_name")

if you use an Enum in SQLAlchemy mapped class, you do not need to add create_constraint=True, since it's using a native enum, which already constrains the values.

if you get an error when migrating alembic due to a circular dependency, you can use use_alter=True in the foreign key definition.

always use "async with session.begin()" instead of weird blocks with commit() and rollback(). In the path operation functions, this should not be needed since the dependency manages the transaction. If you need to have an error and not rollback, you will have to use a nested transaction.

remember to do flush after altering the objects for them to get sent to the database, since autoflush is off.

When adding a new model, make sure to import it or the file it's in in the database.py file.
If you get errors like "When initializing mapper Mapper[] expression '' failed to locate a name ('')", it means you need to import the model in the database.py file.

Don't use column_property with alias, since it will force some early evaluation and break things. Use hybrid_property instead.

If you use an third mapped class as a many to many table, add viewonly=True to the relationship connecting the two other mapped classes to avoid conflicts.

As defined in the type_annotation_map in base.py, mapped datetimes always use timezone=True, so no need to specify it.

# Alembic cheat sheet:
After changing models, run:
alembic revision --autogenerate -m "message"

to apply one migration:
alembic upgrade +1

to apply the migrations:
alembic upgrade head

to revert one migration:
alembic downgrade -1

to revert all migrations:
alembic downgrade base

to list migrations:
alembic history


# Choices i made

## Poetry

I used to use pipenv, but i now think Poetry is better.

## Uvicorn

Well maintained, actively developed, production ready. I wanted to use Granian, which is written in Rust, but it's less maintained. I didn't benchmark anything, and I could do this
in the future if desired.

## FastAPI

Better maintained than django ninja. Everything makes more sense. 

## Database

I chose Postgres. It's a reliable, mature database that is battle-tested.

## SQLAlchemy

I chose SQLAlchemy. It's a very powerful ORM that is well maintained and has async support. Massive improvements over the Django ORM, which is synchronous and way less flexible.

## Asynchronous

I chose to use async for the database operations and the API. This should be an improvement over the Django api, which was asynchronous but the underlying ORM was still blocking,
so queries had to run in a thread outside of the event loop.

## Arq

I chose Arq for the task queue. I was afraid that it wasn't used or maintained enough. No new versions in 2024, for example (in 2025 there was one). But since it's very simple and easy to use, I decided to give it a try. I chose it instead of Celery because of the async support. I also did not choose taskiq because there were less github stars, and i also think i would have had to implement the redis broker on my own (since their implementation is not recommended for production).


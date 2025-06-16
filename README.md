# Development Guidelines

## Python

- Use type hints for everything that type checking in strict mode requires.
- Think about the interface of functions and consider forcing the caller to pass some parameters as kwargs instead of positional arguments by using "*" before the kwargs. This is especially useful for service functions and functions with many parameters. It makes it easier to change parameters and to add new parameters in the future, since the order of the parameters is not important.

## Database Schema Design

- If a column needs unique=True, don't add index=True, because PostgreSQL automatically creates an index for unique constraints.
- As defined in the type_annotation_map in base.py, mapped datetimes always use timezone=True, so no need to specify it.
- As defined in base.py, all tables have tablename defined, an id column and a created_at column. They are all also DataclassAsMapped, so be mindful of how the constructor for the dataclass will be created, depdending on what you do with the mapped_columns. The current convention for required foreign keys is to set default=None on both the _id and the relationship attribute, even though that is not the best for type checking (since one of them has to be passed but this will not be enforced statically). Prefer to use kw_only=True on the mapped classes. Also, use default_factory=list for list relationship sides.
- When defining a column for a subclass and using single table inheritance, choose its type as non-nullable as in "Mapped[int]" but set nullable=True in the mapped_column definition of the new column. No need to set a default, it will be set to null. We do it like this because not all subclasses will have the new column, and it's better to have a nullable column than a non-nullable column with a default. Or, if dealing with a relationship, define the relationship attribute and the foreign key attribute in the subclass like "Mapped["ChildClass"]" and "child_id: Mapped[int]" but pass nullable=True to the foreign key mapped_column.
- Don't use column_property with alias, since it will force some early evaluation and break things. Use hybrid_property instead.
- If you use a third mapped class as a many-to-many table, add viewonly=True to the relationship connecting the two other mapped classes to avoid conflicts.
- Use lazy="raise_on_sql" basically always on relationships, we don't want to do db access implicitly (even though using async sqlalchemy would already block this implicit db access, i prefer to be explicit). When you want to define a "strong" relationship, where a child should be deleted if the parent is, you probably want to use the following, plus any other kwargs you want to pass to the relationship:
- ~~if you add a geoalchemy2 column, you may have to remove from the migration file the "create_index", because the column definition may already create the index~~. This is not needed anymore, since we are using the env.py file to skip the creation of those indexes.
```python
relationship(
    lazy="raise_on_sql",
    cascade=ASYNC_PARENT_FOREIGN_KEY_OPTIONS,
    passive_deletes=True,
)
```

## SQLAlchemy Usage

- Always use "async with session.begin()" instead of explicit commit() and rollback() blocks. In path operation functions, this should not be needed since the dependency manages the transaction. autobegin is off to promote explicit control of transactions. If you need to have an error and not rollback when inside a transaction context (such as in a router function), use a nested transaction.
- Remember to do flush after altering objects to send changes to the database, since autoflush is off. This was chosen so that we know exactly when we are hitting the database.


## FastAPI Usage

- Prefer to return the pydantic models directly in the router functions, instead of using response_model=... and returning your ORM models. This is better because it allows for better type checking. And don't create those pydantic models using model_validate, because model_validate doesn't give linting errors.
- To make this more reusable, consider adding a classmethod on the pydantic model that takes in a db model and constructs the pydantic model instance. Or alternatively, create a function inside routers.py that takes an ORM model and returns a pydantic model.
- The DBSessionAnnotated dependency takes care of committing, so don't call await db_session.commit() in the router function (or in services).


# Common Commands

Run them from the root directory.

## Alembic

After changing models, run this to create a new migration:

```bash
alembic revision --autogenerate -m "message"
```

To apply one migration:

```bash
alembic upgrade +1
```

To apply all migrations:

```bash
alembic upgrade head
```

To revert one migration:

```bash
alembic downgrade -1
```

To revert all migrations:

```bash
alembic downgrade base
```

To list migrations:

```bash
alembic history
```

## Application

To start the server:

```bash
python -m app.main
```

To start the worker:

```bash
python -m app.arq_worker
```

To run tests:

```bash
pytest
```
Add -x to exit on first failure.

To run tests at max speed by using more cores:

```bash
pytest -n auto
```
note: this will not output live logs, only on test.log.

To run django tests:

```bash
PYTHONPATH=./pico_django python -m pico_django.manage test
```

To migrate django:
```bash
PYTHONPATH=./pico_django python -m pico_django.manage migrate
```

## Docker

To run the setup in docker compose:

```bash
sudo docker compose --file docker-compose.yml up --build --abort-on-container-exit
```


To run tests in docker compose:

```bash
sudo docker compose --file docker-compose-test.yml up --build --abort-on-container-exit
```




# Choices i made

## Poetry

I used to use pipenv, but i now think Poetry is better.

## Uvicorn

Well maintained, actively developed, production ready. I wanted to use Granian, which is written in Rust, but it's less maintained. I didn't benchmark anything, and I could do this in the future if desired.

## FastAPI

Better maintained than django ninja. Everything makes more sense. 

## Database

I chose Postgres. It's a reliable, mature database that is battle-tested.

## SQLAlchemy

I chose SQLAlchemy. It's a very powerful ORM that is well maintained and has async support. Massive improvements over the Django ORM, which is synchronous and way less flexible.

### Enums

I started using non native enums, because the native ones are badly supported by alembic and gave a lot of headaches.

## Asynchronous

I chose to use async for the database operations and the API. This should be an improvement over the Django api, which was asynchronous but the underlying ORM was still blocking, so queries had to run in a thread outside of the event loop.

## Arq

I chose Arq for the task queue. I was afraid that it wasn't used or maintained enough. No new versions in 2024, for example (in 2025 there was one though). But since it's very simple and easy to use, I decided to give it a try. I chose it instead of Celery because of the async support. I also did not choose taskiq because there were less github stars, and i also think i would have had to implement the redis broker on my own (since their implementation is not recommended for production).


## Dependencies

In the beginning i thought i would have a worker dependencies group, but i decided to not do that because it would make dependencies more complex to manage.
I would have to take care not to import certain modules from the worker functions, so that the worker doesn't require them.
So now the dependency groups just reflect different stages of the development process:

- dev: dependencies for development
- test: dependencies for testing
- project dependencies: dependencies for the app and the worker

## Mocking and faking external services in dev and in tests

Before, we used to use unittest.mock to fake external services. Now, we use a "cheap dependency injection" approach.
Each module that talks to an external service should have a module level variable that is used by the rest of the functions in the module. This variable has the bare minimum implementation of the external service. It is initialized in the module level by checking a setting from config.py and setting the appropriate value (e.g. openai_request = call_openai if settings.environment == Environment.PROD else mock_call_openai).
If desired, the module can have a "protocol" class that defines the interface of the service, and the module level variable can be of that type.
Furthermore, the module can have an inject_{service_name} function that takes the service as an argument and injects it into the module level variable. This is a workaround so that type checkers can detect that the module level variable is of the correct type. If you were to just assign the service to the module level variable directly, they don't complain if you get the type wrong.

## Django

Django inside fastapi as a transition period. Had to add pico_backend to the python path to make it work.
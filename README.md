# Development Guidelines

## Database Schema Design

- If a column needs unique=True, don't add index=True, because PostgreSQL automatically creates an index for unique constraints.
- As defined in the type_annotation_map in base.py, mapped datetimes always use timezone=True, so no need to specify it.
- When defining a subclass and using single table inheritance, choose the type as non-nullable as in "Mapped[int]" but set nullable=True in the mapped_column definition. No need to set a default, it will be set to null.

## SQLAlchemy Usage

- Always use "async with session.begin()" instead of explicit commit() and rollback() blocks. In path operation functions, this should not be needed since the dependency manages the transaction. If you need to have an error and not rollback, use a nested transaction.
- Remember to do flush after altering objects to send changes to the database, since autoflush is off.
- Don't use column_property with alias, since it will force some early evaluation and break things. Use hybrid_property instead.
- If you use a third mapped class as a many-to-many table, add viewonly=True to the relationship connecting the two other mapped classes to avoid conflicts.

## Enum Handling

- If you create an enum in a migration, you may need to add this to the downgrade function:

```python
op.execute("DROP TYPE enum_name")
```



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
arq app.arq_worker.WorkerSettings --watch app
```

To run tests:

```bash
pytest
```

To run tests at max speed by using more cores:

```bash
pytest -n auto
```

To run django tests:

```bash
PYTHONPATH=./pico_django python -m pico_django.manage test
```

To migrate django:
```bash
PYTHONPATH=./pico_django python -m pico_django.manage migrate
```

## Docker

To build the docker image:

```bash
sudo docker compose -f docker-compose-test.yml build
```

To run tests in docker compose:

```bash
sudo docker compose -f docker-compose-test.yml up
```




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
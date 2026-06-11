from typing import Any

import anyio
import sqladmin._queries
import sqladmin.models
from fastapi import Request


class StrictQuery(sqladmin._queries.Query):
    def _insert_sync(self, data: dict[str, Any], request: Request) -> Any:
        obj = self.model_view.model(**self._prefilter(data))
        with self.model_view.session_maker(expire_on_commit=False) as session:
            anyio.from_thread.run(
                self.model_view.on_model_change, data, obj, True, request
            )
            obj = self._set_attributes_sync(
                session, obj, data
            )  # still handles relations
            session.add(obj)
            session.commit()
            anyio.from_thread.run(
                self.model_view.after_model_change, data, obj, True, request
            )
        return obj

    async def _insert_async(self, data: dict[str, Any], request: Request) -> Any:
        obj = self.model_view.model(**self._prefilter(data))
        async with self.model_view.session_maker(expire_on_commit=False) as session:
            await self.model_view.on_model_change(data, obj, True, request)
            obj = await self._set_attributes_async(session, obj, data)
            session.add(obj)
            await session.commit()
            await self.model_view.after_model_change(data, obj, True, request)
        return obj

    def _prefilter(self, data: dict[str, Any]) -> dict[str, Any]:
        cols = {c.key for c in self.model_view._mapper.columns}  # type: ignore
        return {k: v for k, v in data.items() if k in cols}


def monkey_patch_sqladmin():
    """Needed because SQLAdmin does not like sqlalchemy mapped as dataclasses. It instantiates the model without any data and then adds stuff later.
    We override it to instantiate passing the data."""
    sqladmin._queries.Query = StrictQuery
    sqladmin.models.Query = StrictQuery

"""CasePresenter — serialization for ServiceCase."""

from src.presenters.base import Presenter
from src.models.service_case import ServiceCase


class CasePresenter(Presenter):

    def _serialize(self, case: ServiceCase, customer_name: str | None = None) -> dict:
        return {
            "id": case.id,
            "case_number": case.case_number,
            "title": case.title,
            "customer_id": case.customer_id,
            "customer_name": customer_name,
            "status": case.status,
            "priority": case.priority,
            "assigned_to_user_id": case.assigned_to_user_id,
            "assigned_to_name": case.assigned_to_name,
            "source": case.source,
            "job_count": case.job_count,
            "open_job_count": case.open_job_count,
            "thread_count": case.thread_count,
            "invoice_count": case.invoice_count,
            "total_invoiced": case.total_invoiced,
            "total_paid": case.total_paid,
            "created_by": case.created_by,
            "created_at": self._iso(case.created_at),
            "updated_at": self._iso(case.updated_at),
            "closed_at": self._iso(case.closed_at),
        }

    async def one(self, case: ServiceCase) -> dict:
        customer_name = None
        if case.customer_id:
            customers = await self._load_customers({case.customer_id})
            cust = customers.get(case.customer_id)
            if cust:
                customer_name = cust.display_name
        return self._serialize(case, customer_name)

    async def many(self, cases: list[ServiceCase]) -> list[dict]:
        customer_ids = {c.customer_id for c in cases if c.customer_id}
        customers = await self._load_customers(customer_ids)
        return [
            self._serialize(c, customers.get(c.customer_id, None) and customers[c.customer_id].display_name)
            for c in cases
        ]

"""InvoicePresenter — single source of truth for Invoice serialization.

Resolves:
- customer relationship → display_name
- line_items relationship → structured list
"""

from src.presenters.base import Presenter
from src.models.invoice import Invoice


class InvoicePresenter(Presenter):
    """Present Invoice data with resolved customer name."""

    async def many(self, invoices: list[Invoice]) -> list[dict]:
        """Present a list of invoices with batch-loaded customer names."""
        # Invoice model already has customer relationship loaded via selectinload
        return [self._serialize(inv) for inv in invoices]

    async def one(self, invoice: Invoice) -> dict:
        return self._serialize(invoice)

    def _serialize(self, inv: Invoice) -> dict:
        d = {
            "id": inv.id,
            "customer_id": inv.customer_id,
            "customer_name": inv.customer.display_name if inv.customer else None,
            "invoice_number": inv.invoice_number,
            "case_id": inv.case_id if hasattr(inv, "case_id") else None,
            "document_type": inv.document_type if hasattr(inv, "document_type") else "invoice",
            "subject": inv.subject,
            "status": inv.status,
            "issue_date": inv.issue_date.isoformat() if inv.issue_date else None,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "subtotal": float(inv.subtotal or 0),
            "discount": float(inv.discount or 0),
            "tax_rate": float(inv.tax_rate or 0),
            "tax_amount": float(inv.tax_amount or 0),
            "total": float(inv.total or 0),
            "amount_paid": float(inv.amount_paid or 0),
            "balance": float(inv.balance or 0),
            "paid_date": inv.paid_date.isoformat() if inv.paid_date else None,
            "notes": inv.notes,
            "approved_at": self._iso(inv.approved_at) if hasattr(inv, "approved_at") else None,
            "approved_by": inv.approved_by if hasattr(inv, "approved_by") else None,
            "revision_count": inv.revision_count if hasattr(inv, "revision_count") else 0,
            "revised_at": self._iso(inv.revised_at) if hasattr(inv, "revised_at") else None,
            "sent_at": self._iso(inv.sent_at) if hasattr(inv, "sent_at") else None,
            "viewed_at": self._iso(inv.viewed_at) if hasattr(inv, "viewed_at") else None,
            "created_at": self._iso(inv.created_at),
        }

        if hasattr(inv, "line_items") and inv.line_items:
            d["line_items"] = [
                {
                    "id": li.id,
                    "description": li.description,
                    "quantity": float(li.quantity),
                    "unit_price": float(li.unit_price),
                    "amount": float(li.amount or li.quantity * li.unit_price),
                    "is_taxed": li.is_taxed if hasattr(li, "is_taxed") else False,
                    "sort_order": li.sort_order,
                }
                for li in inv.line_items
            ]
        else:
            d["line_items"] = []

        return d

"""Presenter layer — the single exit point for all API response data.

Every model that has FK references to display data gets a Presenter.
Presenters are async, batch-load related data, and are the ONLY way
data leaves the service layer.

Pattern:
    Router → Service.method() → returns Model(s)
    Router → Presenter.one(model) or Presenter.many(models) → returns dict(s)
"""

from src.presenters.base import Presenter
from src.presenters.action_presenter import ActionPresenter

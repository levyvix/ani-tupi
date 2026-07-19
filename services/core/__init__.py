"""Cross-cutting core services.

Groups app-level services that are not tied to a single content domain:
- history_service: Watch history persistence and AniList reconciliation
- settings_management_service: Runtime settings management
- update_check_service: Application update checks
- ui_bridge: Lazy UI proxies for the service layer

Submodules are imported on demand (this package intentionally does not eagerly
import them) so that lightweight helpers like ``ui_bridge`` stay cheap to import.
"""

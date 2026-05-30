from src.worker.agents.template_analysis.visual_layout_model import VisualModel

def reconcile_visual_evidence(openxml_model: VisualModel, python_docx_model: VisualModel, docling_model: VisualModel) -> VisualModel:
    # OpenXML is the source of truth for tokens and table geometry.
    # We will just pass the openxml model as the reconciled model for now,
    # optionally enriching it with any unique python_docx/docling insights if needed.

    reconciled = VisualModel(
        pages=openxml_model.pages,
        tables=openxml_model.tables,
        blocks=openxml_model.blocks,
        regions=[],
        warnings=docling_model.warnings
    )

    return reconciled

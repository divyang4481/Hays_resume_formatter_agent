from src.worker.agents.template_analysis.visual_layout_model import VisualModel

def extract_docling_visual_evidence(docx_bytes: bytes, filename: str) -> VisualModel:
    model = VisualModel()
    # Mocking docling for now, it's optional
    model.warnings.append("docling_not_available")
    return model

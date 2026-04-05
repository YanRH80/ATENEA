"""
tests/conftest.py — Shared fixtures for ATENEA test suite.

Provides a temporary project directory with sample JSON data
so tests never touch real user data (~/.atenea/data/).
"""

import json
import os
import pytest


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect ATENEA_DATA_DIR to a temp directory for every test."""
    data_dir = str(tmp_path / "data")
    os.makedirs(data_dir, exist_ok=True)
    monkeypatch.setenv("ATENEA_DATA_DIR", data_dir)

    # Force reload of defaults.DEFAULT_DATA_DIR (it reads env at import time)
    import config.defaults as defaults
    monkeypatch.setattr(defaults, "DEFAULT_DATA_DIR", data_dir)

    return data_dir


@pytest.fixture
def sample_project(tmp_data_dir):
    """Create a sample project with knowledge, questions, coverage, sessions."""
    project_name = "testproj"
    project_dir = os.path.join(tmp_data_dir, project_name)
    os.makedirs(project_dir, exist_ok=True)

    # project.json
    _write(project_dir, "project.json", {
        "name": project_name,
        "schema_version": 1,
    })

    # knowledge.json
    _write(project_dir, "knowledge.json", {
        "keywords": [
            {"term": "hipertension", "definition": "Presion arterial elevada", "source": "doc1", "tags": ["cardio"]},
            {"term": "diabetes", "definition": "Trastorno metabolico", "source": "doc1", "tags": ["endocrino"]},
            {"term": "insulina", "definition": "Hormona pancreatica", "source": "doc2", "tags": ["endocrino"]},
            {"term": "estatinas", "definition": "Farmacos hipolipemiantes", "source": "doc2", "tags": ["cardio"]},
            {"term": "metformina", "definition": "Antidiabetico oral", "source": "doc2", "tags": ["endocrino"]},
        ],
        "associations": [
            {"from_term": "diabetes", "to_term": "insulina", "relation": "regulada_por", "source": "doc1"},
            {"from_term": "hipertension", "to_term": "estatinas", "relation": "tratada_con", "source": "doc2"},
        ],
        "sequences": [
            {"id": "seq1", "description": "Cascada metabolica", "nodes": ["diabetes", "insulina", "metformina"], "source": "doc1"},
        ],
    })

    # questions.json — 6 questions targeting different concepts
    _write(project_dir, "questions.json", {
        "questions": [
            _question("q1", "Que causa hipertension?", "A", targets=["hipertension"]),
            _question("q2", "Funcion de insulina?", "B", targets=["insulina"]),
            _question("q3", "Tipo de diabetes?", "C", targets=["diabetes"]),
            _question("q4", "Mecanismo estatinas?", "A", targets=["estatinas"]),
            _question("q5", "Dosis metformina?", "D", targets=["metformina"]),
            _question("q6", "Relacion diabetes-insulina?", "B", targets=["diabetes", "insulina"]),
        ],
    })

    # coverage.json — mixed states
    _write(project_dir, "coverage.json", {
        "items": {
            "hipertension": {"ef": 2.5, "interval": 6.0, "reviews": 3, "correct": 3, "status": "known"},
            "diabetes": {"ef": 2.2, "interval": 1.0, "reviews": 2, "correct": 1, "status": "testing"},
            # insulina, estatinas, metformina = unknown (not in items)
        },
    })

    # sessions.json
    _write(project_dir, "sessions.json", {
        "sessions": [
            {"date": "2026-04-01T10:00:00Z", "total": 5, "correct": 3, "score": 60.0, "results": []},
            {"date": "2026-04-03T10:00:00Z", "total": 5, "correct": 4, "score": 80.0, "results": []},
        ],
    })

    return project_name


def _write(directory, filename, data):
    with open(os.path.join(directory, filename), "w") as f:
        json.dump(data, f)


def _question(qid, text, correct, targets):
    return {
        "id": qid,
        "question": text,
        "correct": correct,
        "options": {"A": "Opcion A", "B": "Opcion B", "C": "Opcion C", "D": "Opcion D", "E": "Opcion E"},
        "justification": f"Justificacion para {qid}",
        "targets": targets,
        "pattern": "direct_recall",
        "difficulty": 1,
    }

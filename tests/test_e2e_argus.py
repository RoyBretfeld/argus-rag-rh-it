# E2E Integrationstests für Argus RAG
# Testet echte HTTP-Requests gegen das laufende API-Backend auf localhost:8000

import unittest
import requests
import os
import time
from pathlib import Path

API_URL = "http://localhost:8000/api"

class TestArgusE2E(unittest.TestCase):
    """End-to-End Integrationstests für das Argus RAG-System."""

    @classmethod
    def setUpClass(cls):
        """Prüft, ob die API erreichbar ist, bevor die Tests starten."""
        try:
            res = requests.get(f"{API_URL}/health", timeout=5)
            if res.status_code != 200 or res.json().get("status") != "ok":
                raise RuntimeError("API health check failed.")
        except Exception as e:
            raise unittest.SkipTest(f"Laufendes API-Backend nicht erreichbar unter {API_URL}: {e}")

    def setUp(self):
        """Vor jedem Test stellen wir sicher, dass wir in einem sauberen Zustand sind."""
        # Datenbank zurücksetzen
        requests.post(f"{API_URL}/system/reset")
        time.sleep(0.5)

    def tearDown(self):
        """Nach jedem Test sauber aufräumen."""
        requests.post(f"{API_URL}/system/reset")

    def test_01_ingestion_to_query_e2e(self):
        """TEST 1: Ingestion -> Query E2E (Lokale sensible Collection)"""
        # 1. Temporäre Datei erstellen
        temp_file = Path("tests/fixtures/temp_secret.txt")
        temp_file.parent.mkdir(parents=True, exist_ok=True)
        secret_content = "Der allsehende Argus RAG Code fuer diese Session lautet: Pavo-2026-Super-Safe."
        temp_file.write_text(secret_content, encoding="utf-8")

        try:
            # 2. Datei hochladen (als vertraulich/lokal)
            with open(temp_file, "rb") as f:
                upload_res = requests.post(
                    f"{API_URL}/upload",
                    files={"files": (temp_file.name, f, "text/plain")},
                    data={"kategorie": "dokumente", "vertraulich": "true"}
                )
            
            self.assertEqual(upload_res.status_code, 200)
            upload_data = upload_res.json()
            self.assertIn("chunks_erstellt", upload_data)
            self.assertTrue(upload_data["chunks_erstellt"] > 0)

            # Kurz warten, bis ChromaDB die Vektoren verarbeitet hat
            time.sleep(1.0)

            # 3. Anfrage an den Chat-Endpunkt stellen
            chat_res = requests.post(
                f"{API_URL}/chat",
                json={
                    "frage": "Wie lautet der allsehende Argus RAG Code für diese Session?",
                    "modus": "wissensbasis",
                    "vertraulich": True
                }
            )
            
            self.assertEqual(chat_res.status_code, 200)
            chat_data = chat_res.json().get("response", {})
            
            # Verifizieren, dass die Antwort das Geheimnis enthält
            self.assertIn("Pavo-2026-Super-Safe", chat_data.get("antwort", ""))
            
            # Verifizieren, dass das hochgeladene Dokument als Quelle angegeben wird
            quellen = chat_data.get("rag_quellen", [])
            self.assertTrue(len(quellen) > 0)
            self.assertEqual(quellen[0]["quelle"], temp_file.name)

        finally:
            if temp_file.exists():
                temp_file.unlink()

    def test_02_metadata_filtering_e2e(self):
        """TEST 2: Metadaten-Filterung E2E"""
        # 1. Zwei Dateien mit unterschiedlicher Kategorie hochladen
        file_doc = Path("tests/fixtures/temp_doc.txt")
        file_data = Path("tests/fixtures/temp_data.csv")
        file_doc.write_text("Das ist ein normaler Dokumententext für die Suche.", encoding="utf-8")
        file_data.write_text("ID,Wert,Beschreibung\n1,100,Tabelleneintrag fuer Argus.", encoding="utf-8")

        try:
            with open(file_doc, "rb") as f1, open(file_data, "rb") as f2:
                # Normales Dokument
                requests.post(
                    f"{API_URL}/upload",
                    files={"files": (file_doc.name, f1, "text/plain")},
                    data={"kategorie": "dokumente", "vertraulich": "true"}
                )
                # Technisches Daten-Dokument
                requests.post(
                    f"{API_URL}/upload",
                    files={"files": (file_data.name, f2, "text/csv")},
                    data={"kategorie": "technische_daten", "vertraulich": "true"}
                )

            time.sleep(1.0)

            # 2. Chat-Anfrage mit Metadatenfilter: Nur "technische_daten" (csv) durchsuchen
            chat_res = requests.post(
                f"{API_URL}/chat",
                json={
                    "frage": "Zeige mir den Tabelleneintrag.",
                    "modus": "wissensbasis",
                    "vertraulich": True,
                    "filter_metadata": {"kategorie": "technische_daten"}
                }
            )
            
            self.assertEqual(chat_res.status_code, 200)
            chat_data = chat_res.json().get("response", {})
            quellen = chat_data.get("rag_quellen", [])
            
            # Verifizieren, dass NUR das CSV-Dokument geliefert wurde
            self.assertTrue(len(quellen) > 0)
            for q in quellen:
                self.assertEqual(q["quelle"], file_data.name)
                self.assertNotEqual(q["quelle"], file_doc.name)

        finally:
            if file_doc.exists():
                file_doc.unlink()
            if file_data.exists():
                file_data.unlink()

    def test_03_hybrid_search_precision_e2e(self):
        """TEST 3: Hybrid Search (BM25 Schlüsselwort-Relevanz für Seriennummern)"""
        # 1. Dokument mit einer kryptischen Seriennummer hochladen
        temp_file = Path("tests/fixtures/temp_serial.txt")
        temp_file.write_text("Die kritische Komponente hat das Label SerialNumber-CX9876-Alpha.", encoding="utf-8")

        try:
            with open(temp_file, "rb") as f:
                requests.post(
                    f"{API_URL}/upload",
                    files={"files": (temp_file.name, f, "text/plain")},
                    data={"kategorie": "dokumente", "vertraulich": "true"}
                )

            time.sleep(1.0)

            # 2. Query mit exakter Seriennummer (BM25-Stärke)
            chat_res = requests.post(
                f"{API_URL}/chat",
                json={
                    "frage": "Welches Label hat die Komponente SerialNumber-CX9876-Alpha?",
                    "modus": "wissensbasis",
                    "vertraulich": True
                }
            )
            
            self.assertEqual(chat_res.status_code, 200)
            chat_data = chat_res.json().get("response", {})
            self.assertIn("SerialNumber-CX9876-Alpha", chat_data.get("antwort", ""))
            self.assertTrue(len(chat_data.get("rag_quellen", [])) > 0)
            self.assertEqual(chat_data["rag_quellen"][0]["quelle"], temp_file.name)

        finally:
            if temp_file.exists():
                temp_file.unlink()

    def test_04_database_consistency_e2e(self):
        """TEST 4: Datenbank-Konsistenz- & Reset-Validierung"""
        # 1. Ausgangszustand prüfen (sollte leer sein nach setUp reset)
        stats_res1 = requests.get(f"{API_URL}/system/stats")
        self.assertEqual(stats_res1.status_code, 200)
        stats1 = stats_res1.json()
        self.assertEqual(stats1["database"]["nsi_local"], 0)
        self.assertEqual(stats1["database"]["nsi_cloud"], 0)

        # 2. Dokument hochladen
        temp_file = Path("tests/fixtures/temp_stats.txt")
        temp_file.write_text("Inhalt fuer Statistik-Messung.", encoding="utf-8")
        
        try:
            with open(temp_file, "rb") as f:
                requests.post(
                    f"{API_URL}/upload",
                    files={"files": (temp_file.name, f, "text/plain")},
                    data={"kategorie": "dokumente", "vertraulich": "true"}
                )
            
            time.sleep(1.0)
            
            # 3. Statistik prüfen -> Muss 1 Chunk sein
            stats_res2 = requests.get(f"{API_URL}/system/stats")
            stats2 = stats_res2.json()
            self.assertEqual(stats2["database"]["nsi_local"], 1)

            # 4. Zurücksetzen der Datenbank über die API
            reset_res = requests.post(f"{API_URL}/system/reset")
            self.assertEqual(reset_res.status_code, 200)
            time.sleep(0.5)

            # 5. Endzustand prüfen -> Muss wieder 0 sein
            stats_res3 = requests.get(f"{API_URL}/system/stats")
            stats3 = stats_res3.json()
            self.assertEqual(stats3["database"]["nsi_local"], 0)

        finally:
            if temp_file.exists():
                temp_file.unlink()

    def test_05_reranker_resilience_fallback_e2e(self):
        """TEST 5: Re-Ranker Resilience & Fallback-Validierung"""
        # 1. Dokument hochladen
        temp_file = Path("tests/fixtures/temp_resilience.txt")
        temp_file.write_text("Sicherheitsrelevantes Dokument fuer den Resilienz-Test.", encoding="utf-8")
        
        try:
            with open(temp_file, "rb") as f:
                requests.post(
                    f"{API_URL}/upload",
                    files={"files": (temp_file.name, f, "text/plain")},
                    data={"kategorie": "dokumente", "vertraulich": "true"}
                )

            time.sleep(1.0)

            # 2. Anfrage an den Chat-Endpunkt stellen (Re-Ranking läuft im Hintergrund)
            # Da die sentence-transformers Bibliothek eventuell noch nicht geladen/installiert ist,
            # validiert dieser Test den lautlosen Fallback auf RRF-Ergebnisse.
            chat_res = requests.post(
                f"{API_URL}/chat",
                json={
                    "frage": "Sicherheitsrelevantes Dokument",
                    "modus": "wissensbasis",
                    "vertraulich": True
                }
            )
            
            self.assertEqual(chat_res.status_code, 200)
            chat_data = chat_res.json().get("response", {})
            
            # Das System darf nicht abstürzen und muss eine valide Antwort liefern
            self.assertIn("antwort", chat_data)
            self.assertTrue(len(chat_data.get("rag_quellen", [])) > 0)
            self.assertEqual(chat_data["rag_quellen"][0]["quelle"], temp_file.name)

        finally:
            if temp_file.exists():
                temp_file.unlink()


if __name__ == "__main__":
    unittest.main()

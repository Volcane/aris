"""
ARIS — Brazil Agent

Brazil has enacted LGPD and is advancing comprehensive AI legislation:
  - LGPD (Lei Geral de Proteção de Dados, 2020) — in force (baseline already tracked)
  - PL 2338/2023 — Brazilian AI Bill, advancing in Senate 2025
  - ANPD (Autoridade Nacional de Proteção de Dados) — active enforcement
  - Resolution CD/ANPD No. 15/2024 — automated decision-making guidance

Key regulators:
  - ANPD — data protection and AI oversight
  - MCOM (Ministry of Communications) — digital policy
  - Câmara dos Deputados / Senado Federal — legislative pipeline

Sources:
  1. ANPD news feed (Portuguese — Claude translates inline)
  2. Pinned key legislation
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sources.international.base import InternationalAgentBase, parse_date, strip_tags
from config.settings import LOOKBACK_DAYS
from utils.cache import http_get_text, is_ai_relevant, get_logger
from utils.search import is_privacy_relevant, detect_domain

log = get_logger("aris.international.br")

ANPD_RSS = "https://www.gov.br/anpd/pt-br/noticias/RSS"

PINNED_BR = [
    {
        "id":       "BR-PL-2338-2023-AI-BILL",
        "title":    "PL 2338/2023 — Brazilian AI Bill (Senate, 2025)",
        "doc_type": "Bill (Advancing)",
        "date":     "2023-05-09",
        "status":   "Advancing in Senate — expected vote 2025",
        "url":      "https://www25.senado.leg.br/web/atividade/materias/-/materia/157233",
        "agency":   "Senado Federal do Brasil",
        "abstract": (
            "Brazil's AI Bill, sponsored by Senator Rodrigo Pacheco, creates a risk-based "
            "AI governance framework similar to the EU AI Act. Key provisions: risk "
            "classification (minimal, limited, high, unacceptable risk), transparency "
            "obligations for high-risk AI, fundamental rights impact assessments, "
            "accountability chain for developers and deployers, prohibited AI practices "
            "(social scoring, manipulation, real-time biometric surveillance), and "
            "rights for individuals subject to automated decisions. ANPD designated as "
            "primary enforcement authority. Penalty up to 2% of revenue (max R$50M)."
        ),
    },
    {
        "id":       "BR-ANPD-RESOLUTION-15-2024",
        "title":    "ANPD Resolution CD/ANPD No. 15/2024 — Automated Decision-Making",
        "doc_type": "Regulatory Resolution",
        "date":     "2024-04-24",
        "status":   "In Force",
        "url":      "https://www.gov.br/anpd/pt-br/documentos-e-publicacoes/resolucao-cd-anpd-no-15-de-24-de-abril-de-2024.pdf",
        "agency":   "ANPD — Autoridade Nacional de Proteção de Dados",
        "abstract": (
            "ANPD Resolution 15/2024 regulates LGPD Article 20 on automated decision-making. "
            "Requires controllers to: provide meaningful information about automated decisions "
            "affecting data subjects' interests, offer right to request human review of "
            "automated decisions, conduct and document legitimate interest assessments for "
            "automated processing, and implement governance measures for automated systems. "
            "Effective immediately; compliance deadline for full implementation is 2025."
        ),
    },
    {
        "id":       "BR-LGPD-ENFORCEMENT-UPDATE-2024",
        "title":    "LGPD Enforcement — ANPD First Sanctions and Priorities (2024)",
        "doc_type": "Enforcement Update",
        "date":     "2024-06-01",
        "status":   "Active",
        "url":      "https://www.gov.br/anpd/pt-br/noticias",
        "agency":   "ANPD — Autoridade Nacional de Proteção de Dados",
        "abstract": (
            "ANPD issued its first administrative sanctions in 2023-2024, signalling active "
            "enforcement of LGPD. Priority enforcement areas: data breach notifications, "
            "consent mechanisms, DPO appointment, and international data transfers. "
            "Maximum penalty R$50M per infraction. ANPD also published guidance on "
            "legitimate interest, cookies, and children's data. Companies with Brazilian "
            "users must review LGPD compliance, especially automated decision-making provisions."
        ),
    },
]


class BrazilAgent(InternationalAgentBase):
    jurisdiction_code    = "BR"
    jurisdiction_name    = "Brazil"
    region               = "Latin America"
    language             = "pt"
    requires_translation = True  # ANPD publishes in Portuguese; Claude translates inline

    def _pinned(self) -> List[Dict[str, Any]]:
        return [
            self._make_doc(
                id=d["id"], source="br_pinned", doc_type=d["doc_type"],
                title=d["title"], url=d["url"],
                published_date=parse_date(d["date"]),
                agency=d["agency"], status=d["status"],
                full_text=d["abstract"], raw_json=d,
            )
            for d in PINNED_BR
        ]

    def _fetch_anpd_rss(self, lookback_days: int) -> List[Dict[str, Any]]:
        docs  = []
        since = datetime.utcnow() - timedelta(days=lookback_days)
        try:
            xml_text = http_get_text(ANPD_RSS, use_cache=True)
            if not xml_text:
                return docs
            root    = ET.fromstring(xml_text)
            channel = root.find("channel") or root
            for item in channel.findall("item"):
                title  = (item.findtext("title")       or "").strip()
                link   = (item.findtext("link")         or "").strip()
                desc   = strip_tags(item.findtext("description") or "", 2000)
                pub    = parse_date(item.findtext("pubDate") or "")
                if pub and pub < since:
                    continue
                # Brazilian privacy/AI terms in Portuguese
                pt_terms = [
                    "inteligência artificial", "proteção de dados", "tratamento",
                    "decisão automatizada", "lgpd", "anpd", "dados pessoais",
                    "privacidade", "algoritmo", "ia ",
                ]
                combined = f"{title} {desc}".lower()
                if not any(t in combined for t in pt_terms) and \
                   not (is_ai_relevant(combined) or is_privacy_relevant(combined)):
                    continue
                safe = re.sub(r"[^a-z0-9]", "_", title.lower())[:50]
                docs.append(self._make_doc(
                    id=f"BR-ANPD-{safe}", source="br_anpd_rss",
                    doc_type="ANPD News / Guidance",
                    title=title, url=link, published_date=pub,
                    agency="ANPD Brazil", status="Published",
                    full_text=desc or title,
                    raw_json={"title": title, "link": link},
                ))
        except Exception as e:
            log.warning("ANPD RSS failed: %s", e)
        return docs

    def fetch_native(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        docs = self._pinned()
        docs.extend(self._fetch_anpd_rss(lookback_days))
        log.info("Brazil: %d docs", len(docs))
        return docs

    def fetch_secondary(self, lookback_days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        return []

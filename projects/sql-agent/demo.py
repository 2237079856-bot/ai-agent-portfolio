"""Offline demonstration of the archived SQL Agent runner with synthetic data."""

import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import run_eval_7b_v3 as agent


def build_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
            CREATE TABLE invoices (
                InvoiceId INTEGER PRIMARY KEY,
                InvoiceDate TEXT NOT NULL,
                Total REAL NOT NULL
            );
            CREATE TABLE invoice_items (
                InvoiceLineId INTEGER PRIMARY KEY,
                InvoiceId INTEGER REFERENCES invoices(InvoiceId),
                Quantity INTEGER NOT NULL
            );
            INSERT INTO invoices VALUES (1, '2010-02-01', 15), (2, '2011-01-03', 20);
            INSERT INTO invoice_items VALUES (1, 1, 3), (2, 1, 4), (3, 2, 9);
        """)


def evaluate(db: Path, question: str, gold: str, replies: list[str], ordered: bool = False):
    case = ["demo", question, gold]
    if ordered:
        case.append(1)
    with patch.object(agent, "chat", side_effect=[(text, {}) for text in replies]) as chat:
        record = agent.run_case((1, case), db, "offline", agent.schema_text(db))
    return record["attempts"], chat


def main() -> None:
    with TemporaryDirectory() as temp:
        db = Path(temp) / "shop.db"
        build_database(db)

        count_items = """
            SELECT SUM(it.Quantity) FROM invoice_items AS it
            JOIN invoices AS i ON it.InvoiceId = i.InvoiceId
            WHERE i.InvoiceDate >= '2010-01-01' AND i.InvoiceDate < '2011-01-01'
        """
        first = "SELECT SUM(Quantity) FROM invoice_items WHERE InvoiceDate LIKE '2010-%'"
        corrected = """
            SELECT SUM(it.Quantity) FROM invoices i
            JOIN invoice_items it ON i.InvoiceId = it.InvoiceId
            WHERE i.InvoiceDate LIKE '2010-%'
        """
        attempts, chat = evaluate(db, "2010 年卖出了多少件商品？", count_items, [first, corrected])
        assert [a["status"] for a in attempts] == ["error", "ok"]
        assert attempts[1]["rows"] == [(7,)] and attempts[1]["correct"]
        retry = chat.call_args_list[1].args[1][-1]["content"]
        assert first in retry and attempts[0]["error"] in retry
        assert count_items not in retry
        print(f"Execution feedback: {attempts[0]['error']} -> result 7 after one repair.")

        month_template = """
            SELECT strftime('{format}', InvoiceDate), SUM(Total)
            FROM invoices WHERE InvoiceDate LIKE '2011-%' GROUP BY 1 ORDER BY 1
        """
        attempts, chat = evaluate(
            db, "按两位月份展示 2011 年金额。",
            month_template.format(format="%m"),
            [month_template.format(format="%Y-%m")],
            ordered=True,
        )
        assert len(attempts) == chat.call_count == 1
        assert attempts[0]["status"] == "ok" and not attempts[0]["correct"]
        print(f"Semantic mismatch: got {attempts[0]['rows'][0][0]}, expected 01. No retry.")

        blocked = agent.execute_query(db, "UPDATE invoices SET Total = 0")
        assert blocked["status"] == "blocked"
        assert agent.execute_query(db, "SELECT SUM(Total) FROM invoices")["rows"] == [(35.0,)]
        print("Read-only guard: update blocked; synthetic fixture unchanged.")


if __name__ == "__main__":
    main()

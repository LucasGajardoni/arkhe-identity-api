import argparse
import csv
import hashlib
from pathlib import Path

from app.services.facial import FacialService
from app.services.files import load_image


def anonymize(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibra limiar facial com pares genuinos e impostores.")
    parser.add_argument("--pairs", required=True, help="CSV: left_path,right_path,label(genuine|impostor)")
    parser.add_argument("--out", default="calibration_report.csv")
    args = parser.parse_args()
    service = FacialService()
    rows = []
    with open(args.pairs, newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            left = service.generate_embedding(load_image(Path(row["left_path"]).read_bytes())).embedding
            right = service.generate_embedding(load_image(Path(row["right_path"]).read_bytes())).embedding
            rows.append(
                {
                    "left_id": anonymize(row["left_path"]),
                    "right_id": anonymize(row["right_path"]),
                    "label": row["label"],
                    "similarity": service.similarity(left, right),
                }
            )
    thresholds = [round(value / 100, 2) for value in range(50, 100)]
    summary = []
    for threshold in thresholds:
        false_accepts = sum(1 for r in rows if r["label"] == "impostor" and r["similarity"] >= threshold)
        false_rejects = sum(1 for r in rows if r["label"] == "genuine" and r["similarity"] < threshold)
        summary.append({"left_id": "SUMMARY", "right_id": "", "label": f"threshold={threshold}", "similarity": f"FAR={false_accepts};FRR={false_rejects}"})
    with open(args.out, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["left_id", "right_id", "label", "similarity"])
        writer.writeheader()
        writer.writerows(rows)
        writer.writerows(summary)
    print(f"Relatorio anonimizado gerado em {args.out}")


if __name__ == "__main__":
    main()

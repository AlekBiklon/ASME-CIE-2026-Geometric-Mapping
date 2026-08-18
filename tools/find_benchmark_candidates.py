from pathlib import Path
import json
import pandas as pd


# ============================================================
# SETTINGS
# ============================================================

PROJECT_ROOT = Path(
    r"C:\PROGRAMING_PYTHON\2026-08-14_ASME_Hackathon_2026"
)

PARQUET = (
    PROJECT_ROOT
    / "neuralCAD-Edit-data"
    / "edit_192_external"
    / "parquets"
    / "val_edit_all.parquet"
)

# Already used experiments — exclude them
USED_REQUESTS = {
    "SUJ2G2UMJQR7PMBX_1757677048.372038",   # B01
    "SUJ2G2UMJQR7PMBX_1762932921.809779",   # B02
    "B7A2N74ZJBF9MZHU_1770156927.436414",   # B03
}


# ============================================================
# GET INSTRUCTION
# ============================================================

def get_instruction(row):

    # First try request_text
    value = row.get("request_text")

    if isinstance(value, str) and value.strip():
        return value.strip()

    # Then transcript
    transcript = row.get("request_transcript")

    if not isinstance(transcript, str):
        return ""

    try:
        data = json.loads(transcript)

        segments = data.get("segments", [])

        texts = []

        for segment in segments:
            text = segment.get("text", "")

            if text:
                texts.append(text.strip())

        return " ".join(texts).strip()

    except Exception:
        return transcript.strip()


# ============================================================
# CLASSIFY OPERATION
# ============================================================

def classify(text):

    text = text.lower()

    if "chamfer" in text:
        return "CHAMFER"

    if "fillet" in text:
        return "FILLET"

    if (
        "hole" in text
        or "drill" in text
        or "drilled" in text
    ):
        return "HOLE"

    return None


# ============================================================
# MAIN
# ============================================================

print("=" * 100)
print("ASME CIE 2026 — BENCHMARK CANDIDATE SEARCH")
print("=" * 100)

print("\nParquet:")
print(PARQUET)
print("Exists:", PARQUET.exists())

if not PARQUET.exists():
    raise FileNotFoundError(PARQUET)


df = pd.read_parquet(PARQUET)

print("\nDataset rows:", len(df))


candidates = []


for idx, row in df.iterrows():

    request_id = str(row.get("request", ""))

    if request_id in USED_REQUESTS:
        continue

    instruction = get_instruction(row)

    operation = classify(instruction)

    if operation is None:
        continue

    candidates.append({
        "dataset_row": int(idx),
        "operation": operation,
        "request_id": request_id,
        "file_name": str(row.get("file_name", "")),
        "instruction": instruction,
    })


# ============================================================
# PRINT RESULTS
# ============================================================

for operation in ["HOLE", "FILLET", "CHAMFER"]:

    subset = [
        x for x in candidates
        if x["operation"] == operation
    ]

    print("\n")
    print("=" * 100)
    print(operation)
    print("=" * 100)

    print("Candidates:", len(subset))

    for n, item in enumerate(subset, start=1):

        print("\n" + "-" * 100)

        print("Candidate :", n)
        print("Dataset row:", item["dataset_row"])
        print("Request ID :", item["request_id"])
        print("File name  :", item["file_name"])

        print("\nInstruction:")
        print(item["instruction"])


# ============================================================
# SUMMARY
# ============================================================

print("\n")
print("=" * 100)
print("SUMMARY")
print("=" * 100)

for operation in ["HOLE", "FILLET", "CHAMFER"]:

    count = sum(
        1 for x in candidates
        if x["operation"] == operation
    )

    print(f"{operation:<10}: {count}")


print("\nTotal candidates:", len(candidates))

print("\nSEARCH COMPLETE")
import os
import shutil
import time
from photos import inspect_library, process_library

ORIGINAL_LIBRARY_DIR = "iCloud Photos"
PROCESSED_LIBRARY_DIR = "processed-photos"
TARGET_SIZE_MB = 3.0
MIN_QUALITY = 50
QUALITY_STEP = 5
PARALLEL = True
MAX_WORKERS = None

# Test mode: set to a number to only process that many random photos (e.g., 50 for testing)
TEST_MODE = None


def main() -> None:
    prior_metadata = inspect_library(
        ORIGINAL_LIBRARY_DIR, parallel=PARALLEL, sample_size=TEST_MODE
    )

    if os.path.exists(PROCESSED_LIBRARY_DIR):
        shutil.rmtree(PROCESSED_LIBRARY_DIR)

    # Process Library
    start_time = time.perf_counter()
    process_library(
        ORIGINAL_LIBRARY_DIR,
        PROCESSED_LIBRARY_DIR,
        parallel=PARALLEL,
        max_workers=MAX_WORKERS,
        target_size_mb=TARGET_SIZE_MB,
        min_quality=MIN_QUALITY,
        quality_step=QUALITY_STEP,
        sample_size=TEST_MODE,
    )
    elapsed_seconds = time.perf_counter() - start_time

    # Report size reduction
    posterior_metadata = inspect_library(
        PROCESSED_LIBRARY_DIR, parallel=PARALLEL, sample_size=TEST_MODE
    )
    total_size_reduction = (
        prior_metadata["image_size_mb"].sum()
        - posterior_metadata["image_size_mb"].sum()
    )
    percentage_reduction = (
        total_size_reduction / prior_metadata["image_size_mb"].sum() * 100
    )
    reduction_per_image = total_size_reduction / len(prior_metadata)
    print(
        f"Reduced {total_size_reduction:.2f} MB ({percentage_reduction:.2f}%, {reduction_per_image:.2f} MB per image) in total image size."
    )
    print(f"Processing time: {elapsed_seconds / 60:.2f} minutes")


if __name__ == "__main__":
    main()

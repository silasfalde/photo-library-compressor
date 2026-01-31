# Photo Library Compressor

Photo Library Compressor scans a photo library, compresses images to a target size, and organizes the output based on whether GPS metadata exists. It preserves EXIF data when available and can run in parallel for faster processing.

This project was started as a way to make large-scale changes to my iCloud photo library. I wanted to ensure that all images were compressed to a reasonable size, as well as identify all images without location data.

## Features

- Compresses images to a configurable target size (default: 2 MB)
- Preserves EXIF data when present
- Separates photos with missing GPS metadata into a dedicated folder
- Parallel processing for faster runs on multicore machines
- Estimates time for processing larger libraries

## Project Layout

- main.py: Entry point and configuration
- photos.py: Core image processing and metadata utilities
- original-photos/: Input library (sample/test)
- processed-photos/: Output library (generated)

## Requirements

- Python 3.10+
- Packages: pillow, piexif, pandas, tqdm

If you use a virtual environment, make sure it is activated before running the script.

## Quick Start

1. Put your photos in original-photos/ (or change the input path in main.py).
2. Adjust settings in main.py as needed.
3. Run:

   python main.py

The processed photos are written to processed-photos/ with a missing-locations/ subfolder for images without GPS data.

## Configuration

Edit the constants in main.py to customize behavior:

- ORIGINAL_LIBRARY_DIR: Input folder
- PROCESSED_LIBRARY_DIR: Output folder
- TARGET_SIZE_MB: Target max size per image
- MIN_QUALITY: Lowest JPEG quality to allow
- QUALITY_STEP: Decrease in quality per iteration
- PARALLEL: Enable/disable multiprocessing
- MAX_WORKERS: Set number of worker processes (None uses defaults)

## License

MIT

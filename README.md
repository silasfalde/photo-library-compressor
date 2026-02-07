# Photo Library Compressor

Photo Library Compressor scans a photo library, compresses images to a target size, and organizes the output based on GPS metadata. It preserves EXIF data when available, handles slow-processing photos gracefully, and tracks compression performance metrics.

This project was started as a way to make large-scale changes to my iCloud photo library. I wanted to ensure that all images were compressed to a reasonable size, as well as identify all images without location data.

## Features

- Compresses images to a configurable target size (default: 3 MB)
- Preserves EXIF data and metadata efficiently
- Separates photos with missing GPS metadata into a dedicated folder
- Handles slow-processing photos (e.g., iPhone HEIC with computational photography) with configurable timeout
- Tracks compression times and timeout status in output CSV
- Gracefully handles large or complex images that exceed processing time limits
- Supports HEIC/HEIF format via pillow-heif

## Project Layout

- main.py: Entry point and configuration
- photos.py: Core image processing and metadata utilities
- iCloud Photos/: Input library structure
- processed-photos/: Output library (generated)
  - Root: Photos with GPS data
  - missing-locations/: Photos without GPS data
  - problem-photos/: Partially compressed versions of photos that exceeded timeout

## Requirements

- Python 3.10+
- Packages: pillow, pillow-heif, piexif, pandas, tqdm

If you use a virtual environment, make sure it is activated before running the script.

## Quick Start

1. Place your photos in iCloud Photos/ (or change the input path in main.py).
2. Adjust settings in main.py as needed.
3. Run:

   python main.py

The processed photos are written to processed-photos/ with:
- Main directory: All photos with GPS data (both compressed and already compliant)
- missing-locations/: Photos without GPS data (both compressed and already compliant)
- problem-photos/: Copies of photos that exceeded the processing timeout (the original, uncompressed photos, so you'll find partially compressed versions in the main directory)

A complete library with no duplicates is the sum of the photos in both the main directory (processed-photos) and the missing-locations directory.  

## Configuration

Edit the constants in main.py to customize behavior:

- ORIGINAL_LIBRARY_DIR: Input folder
- PROCESSED_LIBRARY_DIR: Output folder
- TARGET_SIZE_MB: Target max size per image (default: 3 MB)
- MIN_QUALITY: Lowest JPEG quality to allow (default: 50)
- QUALITY_STEP: Decrease in quality per iteration (default: 5)
- PROCESSING_TIMEOUT_SECONDS: Max seconds per image before timeout (default: 3.0)
- TEST_MODE: Set to a number to process only that many random photos for testing (None = process all)

## Output

The script generates `results.csv` containing metadata for all processed images, including:
- Original image properties (EXIF, dimensions, GPS coordinates)
- Compressed file size
- Compression time in seconds
- exceeded_timeout: Boolean flag indicating if the image hit the processing timeout

## Handling Slow Photos

Some photos, particularly iPhone HEIC files with computational photography features or complex EXIF data, may take longer to process than others. The processor:

1. Compresses the image with quality decreasing in steps
2. If timeout is exceeded, saves the partially compressed version to problem-photos/
3. Copies the original uncompressed image to the main processed-photos/ directory
4. Marks the image with `exceeded_timeout=True` in results.csv

This ensures you always have usable images in your processed library while preserving the originals as backups.

## Performance Notes

- EXIF processing happens once per image, before the compression loop (not repeatedly)
- Processing time varies significantly based on image format, resolution, and EXIF complexity
- iPhone HEIC files may require more processing time due to auxiliary data structures

MIT

from PIL import Image
import piexif
import os
import pandas as pd
from tqdm import tqdm
import random
import shutil
import time

# Register HEIC support if available
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
except ImportError:
    pass


def _exif_to_tag(exif_dict):
    """Converts EXIF dictionary to a more human-readable tag dictionary."""
    codec = "ISO-8859-1"  # or latin-1
    exif_tag_dict = {}
    thumbnail = exif_dict.pop("thumbnail")
    if thumbnail:
        exif_tag_dict["thumbnail"] = thumbnail.decode(codec)

    for ifd in exif_dict:
        exif_tag_dict[ifd] = {}
        for tag in exif_dict[ifd]:
            try:
                element = exif_dict[ifd][tag].decode(codec)

            except AttributeError:
                element = exif_dict[ifd][tag]

            exif_tag_dict[ifd][piexif.TAGS[ifd][tag]["name"]] = element

    return exif_tag_dict


def _find_all_images(dir) -> list[str]:
    """Performs recursive tree search of the directory and returns a list of all images found."""
    images = []

    for root, dirs, files in os.walk(dir):
        for file in files:
            if file.lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".heic")
            ):
                images.append(os.path.join(root, file))

    return images


def _get_image_metadata(image_path) -> dict | None:
    """Extracts and returns all metadata from an image file."""
    try:
        img = Image.open(image_path)
        exif_data = piexif.load(img.info["exif"])
        if exif_data:
            tags = _exif_to_tag(exif_data)
            flattened_tags = pd.json_normalize(tags, sep="_").to_dict(orient="records")[
                0
            ]
            flattened_tags["image_path"] = image_path
            return flattened_tags

        else:
            return None

    except (KeyError, piexif.InvalidImageDataError):
        return None
    except Exception:
        # Handle HEIC and other unsupported formats gracefully
        return None


def _get_image_metadata_with_size(image_path) -> dict | None:
    metadata = _get_image_metadata(image_path) or {}
    metadata["image_path"] = image_path
    metadata["image_size_mb"] = os.path.getsize(image_path) / (1024 * 1024)
    if "GPS_GPSLatitude" not in metadata:
        metadata["GPS_GPSLatitude"] = pd.NA
    return metadata


def _process_photo(
    image_path: str,
    output_path: str,
    target_size_mb: float = 2.0,
    min_quality: int = 50,
    quality_step: int = 5,
    timeout_seconds: float = 2.0,
) -> tuple[float, bool]:
    """Compressed the photo to be under target_size_mb and copies it to the output path.
    Returns a tuple of (compression_time_seconds, exceeded_timeout)."""
    start_time = time.perf_counter()
    exceeded_timeout = False
    try:
        with Image.open(image_path) as img:
            # Convert HEIC/HEIF to RGB if necessary
            if img.mode in ("RGBA", "P", "LA"):
                # Convert RGBA and palette modes to RGB
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                rgb_img.paste(
                    img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None
                )
                img = rgb_img
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # while image is larger than target size, reduce quality
            quality = 95
            target_size_bytes = int(target_size_mb * 1024 * 1024)
            exif_bytes = img.info.get("exif")

            # Process EXIF data once, outside the loop
            exif_data = None
            if exif_bytes:
                try:
                    exif_data = piexif.dump(piexif.load(exif_bytes))
                except Exception:
                    # If EXIF processing fails, continue without it
                    exif_data = None

            while True:
                # Save at current quality
                if exif_data:
                    img.save(output_path, quality=quality, exif=exif_data)
                else:
                    img.save(output_path, quality=quality)

                # Check if we're done
                if (
                    os.path.getsize(output_path) <= target_size_bytes
                    or quality <= min_quality
                ):
                    break

                # Check if we've exceeded the timeout before continuing
                elapsed = time.perf_counter() - start_time
                if elapsed > timeout_seconds:
                    exceeded_timeout = True
                    break

                quality -= quality_step
    except Exception:
        # If processing fails, try a simple copy with format conversion
        try:
            with Image.open(image_path) as img:
                img.convert("RGB").save(output_path, quality=85)
        except Exception:
            # If all else fails, skip this file
            pass
    return (time.perf_counter() - start_time, exceeded_timeout)


def inspect_library(
    dir,
    show_progress: bool = False,
    sample_size: int | None = None,
) -> pd.DataFrame:
    print("Inspecting library at ", dir)
    image_paths = _find_all_images(dir)

    # If sample_size is specified, randomly sample that many images
    if sample_size is not None and sample_size > 0:
        sample_size = min(sample_size, len(image_paths))
        image_paths = random.sample(image_paths, sample_size)

    metadata_list = []

    iterator = image_paths
    if show_progress:
        iterator = tqdm(iterator, total=len(image_paths), desc="Inspecting images")
    for image_path in iterator:
        metadata = _get_image_metadata_with_size(image_path)
        if metadata is not None:
            metadata_list.append(metadata)

    df = pd.DataFrame(metadata_list)
    if not df.empty:
        df.set_index("image_path", inplace=True)
    return df


def _is_missing_gps(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))  # type: ignore
    except ValueError:
        return False


def _copy_photo_task(args: tuple[str, object, str, str]) -> tuple[str, float, bool]:
    """Copies a photo that's already under target size to the output directory.
    Returns (destination_path, compression_time, exceeded_timeout)."""
    (
        image_path,
        gps_lat,
        output_dir,
        missing_locations_dir,
    ) = args
    if _is_missing_gps(gps_lat):
        destination = os.path.join(missing_locations_dir, os.path.basename(image_path))
    else:
        destination = os.path.join(output_dir, os.path.basename(image_path))

    try:
        shutil.copy2(image_path, destination)
    except Exception:
        pass

    return (destination, 0.0, False)


def _process_photo_task(
    args: tuple[str, object, str, str, float, int, int, str, float],
) -> tuple[str, float, bool]:
    (
        image_path,
        gps_lat,
        output_dir,
        missing_locations_dir,
        target_size_mb,
        min_quality,
        quality_step,
        problem_photos_dir,
        processing_timeout_seconds,
    ) = args
    if _is_missing_gps(gps_lat):
        destination = os.path.join(missing_locations_dir, os.path.basename(image_path))
    else:
        destination = os.path.join(output_dir, os.path.basename(image_path))

    compression_time, exceeded_timeout = _process_photo(
        image_path,
        destination,
        target_size_mb=target_size_mb,
        min_quality=min_quality,
        quality_step=quality_step,
        timeout_seconds=processing_timeout_seconds,
    )

    # If processing exceeded timeout, swap the files:
    # Move compressed version to problem-photos and copy original to destination
    if exceeded_timeout:
        problem_photo_destination = os.path.join(
            problem_photos_dir, os.path.basename(image_path)
        )
        try:
            # Move the partially compressed version to problem-photos
            shutil.move(destination, problem_photo_destination)
            # Copy the original uncompressed image to the main directory
            shutil.copy2(image_path, destination)
        except Exception:
            pass

    return (destination, compression_time, exceeded_timeout)


def process_library(
    input_dir: str,
    output_dir: str,
    target_size_mb: float = 2.0,
    min_quality: int = 50,
    quality_step: int = 5,
    sample_size: int | None = None,
    processing_timeout_seconds: float = 1.0,
) -> tuple[dict[str, float], dict[str, bool]]:
    """Processes the photo library by separating already-compliant photos from those needing compression.
    Returns a tuple of (compression_times_dict, exceeded_timeout_dict) mapping image paths to their respective values.
    """
    os.makedirs(output_dir, exist_ok=True)
    missing_locations_dir = os.path.join(output_dir, "missing-locations")
    os.makedirs(missing_locations_dir, exist_ok=True)
    problem_photos_dir = os.path.join(output_dir, "problem-photos")
    os.makedirs(problem_photos_dir, exist_ok=True)
    metadata = inspect_library(
        input_dir,
        show_progress=False,
        sample_size=sample_size,
    )

    # Separate photos into two groups: those already under target size and those needing compression
    already_compliant = metadata[metadata["image_size_mb"] <= target_size_mb]
    needs_compression = metadata[metadata["image_size_mb"] > target_size_mb]

    compression_times = {}
    exceeded_timeout_flags = {}

    # Process photos that are already compliant (just copy them)
    if len(already_compliant) > 0:
        copy_tasks = [
            (
                image_path,
                already_compliant.loc[image_path, "GPS_GPSLatitude"],
                output_dir,
                missing_locations_dir,
            )
            for image_path in already_compliant.index
        ]

        for task in tqdm(copy_tasks, desc="Copying compliant images", unit="img"):
            destination_path, compression_time, exceeded_timeout = _copy_photo_task(
                task
            )
            compression_times[destination_path] = compression_time
            exceeded_timeout_flags[destination_path] = exceeded_timeout

    # Process photos that need compression
    if len(needs_compression) > 0:
        compress_tasks = [
            (
                image_path,
                needs_compression.loc[image_path, "GPS_GPSLatitude"],
                output_dir,
                missing_locations_dir,
                target_size_mb,
                min_quality,
                quality_step,
                problem_photos_dir,
                processing_timeout_seconds,
            )
            for image_path in needs_compression.index
        ]

        for task in tqdm(compress_tasks, desc="Compressing images", unit="img"):
            destination_path, compression_time, exceeded_timeout = _process_photo_task(
                task
            )
            compression_times[destination_path] = compression_time
            exceeded_timeout_flags[destination_path] = exceeded_timeout

    return (compression_times, exceeded_timeout_flags)

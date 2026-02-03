from PIL import Image
import piexif
import os
import pandas as pd
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor
import random

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
) -> None:
    """Compressed the photo to be under target_size_mb and copies it to the output path."""
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

            while True:
                if exif_bytes:
                    exif_data = piexif.dump(piexif.load(exif_bytes))
                    img.save(output_path, quality=quality, exif=exif_data)
                else:
                    img.save(output_path, quality=quality)
                if (
                    os.path.getsize(output_path) <= target_size_bytes
                    or quality <= min_quality
                ):
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


def inspect_library(
    dir,
    parallel: bool = True,
    max_workers: int | None = None,
    show_progress: bool = False,
    sample_size: int | None = None,
) -> pd.DataFrame:
    image_paths = _find_all_images(dir)

    # If sample_size is specified, randomly sample that many images
    if sample_size is not None and sample_size > 0:
        sample_size = min(sample_size, len(image_paths))
        image_paths = random.sample(image_paths, sample_size)

    metadata_list = []

    if parallel and len(image_paths) > 1:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            iterator = executor.map(_get_image_metadata_with_size, image_paths)
            if show_progress:
                iterator = tqdm(
                    iterator, total=len(image_paths), desc="Inspecting images"
                )
            for metadata in iterator:
                if metadata:
                    metadata_list.append(metadata)
    else:
        iterator = image_paths
        if show_progress:
            iterator = tqdm(iterator, total=len(image_paths), desc="Inspecting images")
        for image_path in iterator:
            metadata = _get_image_metadata_with_size(image_path)
            if metadata:
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


def _process_photo_task(args: tuple[str, object, str, str, float, int, int]) -> None:
    (
        image_path,
        gps_lat,
        output_dir,
        missing_locations_dir,
        target_size_mb,
        min_quality,
        quality_step,
    ) = args
    if _is_missing_gps(gps_lat):
        destination = os.path.join(missing_locations_dir, os.path.basename(image_path))
    else:
        destination = os.path.join(output_dir, os.path.basename(image_path))

    _process_photo(
        image_path,
        destination,
        target_size_mb=target_size_mb,
        min_quality=min_quality,
        quality_step=quality_step,
    )


def process_library(
    input_dir: str,
    output_dir: str,
    parallel: bool = True,
    max_workers: int | None = None,
    target_size_mb: float = 2.0,
    min_quality: int = 50,
    quality_step: int = 5,
    sample_size: int | None = None,
) -> None:
    """Processes the photo library by compressing images and organizing them based on GPS data."""
    os.makedirs(output_dir, exist_ok=True)
    missing_locations_dir = os.path.join(output_dir, "missing-locations")
    os.makedirs(missing_locations_dir, exist_ok=True)
    metadata = inspect_library(
        input_dir,
        parallel=parallel,
        max_workers=max_workers,
        show_progress=False,
        sample_size=sample_size,
    )

    tasks = [
        (
            image_path,
            metadata.loc[image_path, "GPS_GPSLatitude"],
            output_dir,
            missing_locations_dir,
            target_size_mb,
            min_quality,
            quality_step,
        )
        for image_path in metadata.index
    ]

    # Iterate through the dataframe and process files based on GPS data
    if parallel and len(tasks) > 1:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            list(
                tqdm(
                    executor.map(_process_photo_task, tasks),
                    total=len(tasks),
                    desc="Processing images",
                )
            )
    else:
        for task in tqdm(tasks, desc="Processing images"):
            _process_photo_task(task)

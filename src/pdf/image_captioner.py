"""
Image Captioner for RAG multimodal pipeline.

Input:
    image_metadata.jsonl (from image_extractor)

Output:
    image_captions.jsonl
    
Uses BLIP for lightweight image captioning
"""

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8"
    )

from PIL import Image
from transformers import (
    BlipProcessor,
    BlipForConditionalGeneration
)


# ============================================================
# LOAD MODEL
# ============================================================

def load_captioner(
    model_name: str = "Salesforce/blip-image-captioning-base"
):
    """
    Load BLIP model for image captioning
    
    Args:
        model_name: HuggingFace model ID
        
    Returns:
        processor, model
    """
    
    print(f"Loading BLIP model: {model_name}")
    
    processor = BlipProcessor.from_pretrained(
        model_name
    )
    
    model = BlipForConditionalGeneration.from_pretrained(
        model_name
    )
    
    print("✓ Model loaded")
    
    return processor, model


# ============================================================
# GENERATE CAPTION
# ============================================================

def generate_caption(
    image_path: Path,
    processor,
    model,
    max_length: int = 50
) -> str:
    """
    Generate caption for single image
    
    Args:
        image_path: Path to image file
        processor: BLIP processor
        model: BLIP model
        max_length: Maximum caption length
        
    Returns:
        Caption text
    """
    
    try:
        # Load image
        image = Image.open(
            image_path
        ).convert("RGB")
        
        # Process
        inputs = processor(
            images=image,
            return_tensors="pt"
        )
        
        # Generate caption
        outputs = model.generate(
            **inputs,
            max_length=max_length
        )
        
        # Decode
        caption = processor.decode(
            outputs[0],
            skip_special_tokens=True
        )
        
        return caption
        
    except Exception as e:
        print(
            f"✗ Failed to caption {image_path}: {e}"
        )
        return ""


# ============================================================
# PROCESS METADATA
# ============================================================

def caption_images(
    metadata_path: Path,
    output_path: Path
):
    """
    Load image metadata and generate captions
    
    Args:
        metadata_path: image_metadata.jsonl
        output_path: image_captions.jsonl
    """
    
    # Check metadata exists
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Metadata not found: {metadata_path}"
        )
    
    print(f"Loading metadata: {metadata_path}")
    
    # Load all image records
    image_records = []
    
    with metadata_path.open(
        "r",
        encoding="utf-8"
    ) as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                image_records.append(record)
    
    print(f"Found {len(image_records)} images")
    
    if len(image_records) == 0:
        print("No images to caption")
        return
    
    # Load model
    processor, model = load_captioner()
    
    # Create output dir
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )
    
    # Process each image
    caption_records = []
    
    for i, record in enumerate(
        image_records,
        start=1
    ):
        
        image_id = record.get(
            "image_id",
            f"img_{i}"
        )
        
        image_path = Path(
            record["image_path"]
        )
        
        print(
            f"[{i}/{len(image_records)}] "
            f"Captioning: {image_id}"
        )
        
        # Generate caption
        caption = generate_caption(
            image_path,
            processor,
            model
        )
        
        # Create caption record
        caption_record = {
            
            "image_id":
                image_id,
            
            "caption":
                caption,
            
            "source":
                record.get("source", ""),
            
            "page":
                record.get("page", 0),
            
            "image_path":
                record.get("image_path", "")
        
        }
        
        caption_records.append(
            caption_record
        )
    
    # Write captions
    print(f"\nWriting captions: {output_path}")
    
    with output_path.open(
        "w",
        encoding="utf-8"
    ) as f:
        
        for record in caption_records:
            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False
                )
                + "\n"
            )
    
    print("=" * 60)
    print("DONE")
    print(
        f"Captions generated: {len(caption_records)}"
    )
    print(
        f"Output: {output_path}"
    )
    print("=" * 60)


# ============================================================
# CLI
# ============================================================

def main():
    
    parser = argparse.ArgumentParser(
        description="Generate captions for extracted images"
    )
    
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path(
            "data/processed/pdf/image_metadata.jsonl"
        ),
        help="Input image metadata"
    )
    
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/processed/pdf/image_captions.jsonl"
        ),
        help="Output captions"
    )
    
    parser.add_argument(
        "--model",
        type=str,
        default="Salesforce/blip-image-captioning-base",
        help="BLIP model name"
    )
    
    args = parser.parse_args()
    
    caption_images(
        args.metadata,
        args.output
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Top-level orchestration CLI for Face-Blockchain Verifier.
Coordinates face detection, social graph search, and blockchain notarization.
"""

import os
import sys
import warnings
from pathlib import Path

# Suppress background C/C++ engine warnings and deprecations
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
warnings.filterwarnings("ignore")

# Configure UTF-8 encoding for Windows console
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from src.face_processor import FaceProcessor, FaceProcessingError, NoFaceDetectedError
from src.social_searcher import SocialImageSearcher, SearchResult, SocialMatch
from src.blockchain_notary import BlockchainNotary
from src.fingerprint import compute_canonical_fingerprint
from src.exceptions import (
    FaceVerificationError,
    InvalidImageError,
    APIKeyMissingError,
    NoSocialMatchFoundError,
    SocialSearchError,
    RPCConnectionError,
    ContractExecutionError,
    BlockchainNotaryError,
)

console = Console(highlight=False)


def print_error_alert(title: str, message: str, suggestion: str = "") -> None:
    """Renders a formatted error panel for clean, traceback-free error reporting."""
    content = Text()
    content.append(f"[X] {message}\n", style="bold white")
    if suggestion:
        content.append(f"\nRecommendation: {suggestion}", style="dim yellow")

    console.print(
        Panel(
            content,
            title=f"[bold red] ALERT: {title} [/]",
            border_style="red",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )


@click.group()
@click.version_option(version="1.0.0", prog_name="Face-Blockchain Verifier")
def cli():
    """Decentralized Facial Identity & Social Media Provenance Notary CLI."""
    pass


@cli.command("run")
@click.option(
    "--image",
    "-i",
    required=True,
    type=click.Path(exists=False, dir_okay=False, readable=True),
    help="Path to the input image containing a face.",
)
def run_pipeline(image: str):
    """Executes the full pipeline: Face Detection -> Social Search -> Keccak Fingerprinting -> Blockchain Notarization."""
    try:
        image_path = Path(image).resolve()
        if not image_path.exists() or not image_path.is_file():
            raise InvalidImageError(f"Image file does not exist: {image}")

        # Pipeline Initiation Announcement
        header_text = Text()
        header_text.append("FACE-BLOCKCHAIN INTEGRITY PIPELINE\n", style="bold cyan")
        header_text.append("Autonomous Biometric Extraction & Decentralized Notarization\n", style="italic")
        header_text.append("Target Image: ", style="bold white")
        header_text.append(f"{image_path}\n", style="green")

        console.print(
            Panel(
                header_text,
                title="[bold blue] PIPELINE INITIATION [/]",
                border_style="bright_blue",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

        processor = FaceProcessor()
        searcher = SocialImageSearcher()
        notary = BlockchainNotary()

        # Step 1: Detect and Crop Face
        console.print("\n[bold cyan]Step 1:[/] Biometric Face Detection & Cryptographic Hashing")
        with console.status("[bold green]Detecting face & extracting Region of Interest (ROI)...[/]", spinner="dots"):
            crop_result = processor.detect_and_crop(str(image_path))

        crop_path = crop_result.temp_file_path
        face_hash = crop_result.sha256_hash

        step1_table = Table(box=box.SIMPLE_HEAVY, show_header=False, padding=(0, 2))
        step1_table.add_column("Key", style="bold cyan", width=22)
        step1_table.add_column("Value", style="bold white")
        step1_table.add_row("Temporary Crop Path", f"[yellow]{crop_path}[/]")
        step1_table.add_row("Face SHA-256 Digest", f"[bold green]{face_hash}[/]")
        step1_table.add_row("Bounding Box (x1,y1,x2,y2)", f"{crop_result.crop_box}")
        step1_table.add_row("Confidence Score", f"{crop_result.detection_confidence * 100:.1f}%")
        console.print(step1_table)

        # Step 2: Reverse Social Search and Immediate Crop Cleanup
        console.print("\n[bold cyan]Step 2:[/] Reverse Social Graph Search")
        search_result = None
        try:
            with console.status("[bold yellow]Uploading crop to reverse image search index & matching social graph...[/]", spinner="dots"):
                search_result = searcher.search(crop_path)
        finally:
            # Immediately remove temporary crop file after upload
            if os.path.exists(crop_path):
                try:
                    os.remove(crop_path)
                    console.print("[dim italic green][OK] Temporary face crop file removed immediately after upload.[/]")
                except OSError as e:
                    console.print(f"[dim italic yellow]Notice: Failed to delete temp file {crop_path}: {e}[/]")

        # Validate search results
        if not search_result.success:
            if "SERPAPI_KEY is not configured" in search_result.message or "api_key" in search_result.message.lower():
                raise APIKeyMissingError(search_result.message)
            raise SocialSearchError(search_result.message)

        if not search_result.matches:
            raise NoSocialMatchFoundError("Zero matching social media posts discovered for this facial crop.")

        # Display discovered post details in formatted table
        discovered_post = search_result.matches[0]

        social_table = Table(
            title="[bold yellow]Discovered Social Post Details[/]",
            box=box.ROUNDED,
            header_style="bold magenta",
            show_lines=True,
        )
        social_table.add_column("Platform", style="bold yellow", width=16)
        social_table.add_column("Post URL", style="underline blue", overflow="fold", no_wrap=False)
        social_table.add_column("Title", style="white")

        for match in search_result.matches:
            social_table.add_row(match.platform, match.post_url, match.title)

        console.print(social_table)

        # Step 3: Compute Canonical 32-byte Keccak-256 Fingerprint
        console.print("\n[bold cyan]Step 3:[/] Constructing Canonical Keccak-256 Fingerprint")
        with console.status("[bold magenta]Encoding biometric payload + social provenance schema...[/]", spinner="dots"):
            fingerprint = compute_canonical_fingerprint(
                face_hash=face_hash,
                platform=discovered_post.platform,
                post_url=discovered_post.post_url,
            )

        fp_panel_content = Text()
        fp_panel_content.append("Canonical Formula: ", style="bold")
        fp_panel_content.append("keccak256(canonical_json({'face_hash', 'platform', 'post_url'}))\n", style="italic dim")
        fp_panel_content.append("Linked Fingerprint: ", style="bold white")
        fp_panel_content.append(f"{fingerprint}\n", style="bold magenta")
        console.print(
            Panel(
                fp_panel_content,
                title="[bold magenta] 32-BYTE KECCAK-256 FINGERPRINT [/]",
                border_style="magenta",
                box=box.ROUNDED,
                padding=(0, 2),
            )
        )

        # Step 4: Notarize Fingerprint on Blockchain
        console.print("\n[bold cyan]Step 4:[/] Decentralized Blockchain Notarization")
        with console.status("[bold blue]Broadcasting transaction to EVM notary contract...[/]", spinner="dots"):
            notarization = notary.notarize_fingerprint(
                fingerprint=fingerprint,
                metadata_uri=f"ipfs://provenance/{discovered_post.platform.lower().replace('/', '_')}/{face_hash[:16]}"
            )

        # Green Confirmation Panel
        success_content = Text()
        success_content.append("[OK] State transition successfully confirmed on immutable ledger.\n\n", style="bold white")
        success_content.append("Transaction Hash : ", style="bold white")
        success_content.append(f"{notarization['tx_hash']}\n", style="bold yellow")
        success_content.append("Block Number     : ", style="bold white")
        success_content.append(f"#{notarization['block_number']}\n", style="bold cyan")
        success_content.append("Network          : ", style="bold white")
        success_content.append(f"{notarization['network']}\n", style="bold green")
        success_content.append("Submitter        : ", style="bold white")
        success_content.append(f"{notarization['submitter']}\n", style="dim")
        success_content.append("Metadata Link    : ", style="bold white")
        success_content.append(f"{notarization['metadata_uri']}", style="underline blue")

        console.print(
            Panel(
                success_content,
                title="[bold green] NOTARIZATION SUCCESSFUL [/]",
                border_style="bold green",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

        platform = discovered_post.platform
        post_url = discovered_post.post_url

        console.print(f"\n[bold cyan]Notarized Platform:[/] {platform}")
        console.print(f"[bold cyan]Notarized Post URL:[/] {post_url}")

        console.print("\n[bold green]To verify this authentic record on-chain, run:[/bold green]")
        console.print(f"python main.py verify --image {image} --platform \"{platform}\" --post-url \"{post_url}\"\n")
        console.print("[bold yellow]To test tamper detection, run:[/bold yellow]")
        console.print(f"python main.py verify --image {image} --platform \"{platform}\" --post-url \"{post_url}/tampered\"\n")

    except InvalidImageError as e:
        print_error_alert("INVALID IMAGE INPUT", str(e), "Verify the image file path, permissions, and image format (.jpg, .png, .jpeg).")
        sys.exit(1)
    except NoFaceDetectedError as e:
        print_error_alert("NO FACE DETECTED", str(e), "Provide an image with a visible, unobstructed frontal face portrait.")
        sys.exit(1)
    except FaceProcessingError as e:
        print_error_alert("FACE PROCESSING ERROR", str(e), "Check image quality or try a higher-resolution portrait.")
        sys.exit(1)
    except APIKeyMissingError as e:
        print_error_alert("AUTHENTICATION ERROR", str(e), "Set SERPAPI_KEY in your .env or environment variables.")
        sys.exit(1)
    except NoSocialMatchFoundError as e:
        print_error_alert("NO SOCIAL MATCHES FOUND", str(e), "Ensure the face image has been indexed on public social platforms.")
        sys.exit(1)
    except SocialSearchError as e:
        print_error_alert("SOCIAL SEARCH FAILED", str(e), "Check your internet connectivity or SerpApi quota.")
        sys.exit(1)
    except RPCConnectionError as e:
        print_error_alert("RPC NODE UNREACHABLE", str(e), "Ensure RPC_URL points to an active, responsive EVM node or testnet provider.")
        sys.exit(1)
    except ContractExecutionError as e:
        print_error_alert("SMART CONTRACT ERROR", str(e), "Verify your gas balance, contract address, and network compatibility.")
        sys.exit(1)
    except BlockchainNotaryError as e:
        print_error_alert("BLOCKCHAIN NOTARY ERROR", str(e), "Review your Web3 credentials and transaction parameters.")
        sys.exit(1)
    except Exception as e:
        print_error_alert("UNEXPECTED SYSTEM ERROR", str(e), "Check system logs or contact support.")
        sys.exit(1)


@cli.command("verify")
@click.option(
    "--image",
    "-i",
    required=True,
    type=click.Path(exists=False, dir_okay=False, readable=True),
    help="Path to the query face image.",
)
@click.option(
    "--post-url",
    "-u",
    required=True,
    type=str,
    help="Published social post URL claimed to host this image.",
)
@click.option(
    "--platform",
    "-p",
    required=True,
    type=str,
    help="Social platform name (e.g., 'X/Twitter', 'Instagram', 'LinkedIn').",
)
def verify_pipeline(image: str, post_url: str, platform: str):
    """Verifies authenticity and integrity by reconstructing the Keccak-256 fingerprint against the blockchain."""
    try:
        image_path = Path(image).resolve()
        if not image_path.exists() or not image_path.is_file():
            raise InvalidImageError(f"Image file does not exist: {image}")

        console.print(
            Panel(
                f"[bold cyan]Query Image:[/] {image_path}\n"
                f"[bold cyan]Claimed URL:[/] {post_url}\n"
                f"[bold cyan]Platform   :[/] {platform}",
                title="[bold blue] ON-CHAIN INTEGRITY VERIFICATION [/]",
                border_style="bright_blue",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )

        processor = FaceProcessor()
        notary = BlockchainNotary()

        # Step 1: Re-process input face to retrieve face hash
        with console.status("[bold cyan]Re-extracting facial biometric signature...[/]", spinner="dots"):
            face_hash = processor.get_face_hash(str(image_path))

        console.print(f"[dim]* Computed Face Digest:[/] [bold green]{face_hash}[/]")

        # Step 2: Reconstruct canonical Keccak-256 payload hash
        fingerprint = compute_canonical_fingerprint(
            face_hash=face_hash,
            platform=platform,
            post_url=post_url,
        )
        console.print(f"[dim]* Reconstructed Keccak-256 Fingerprint:[/] [bold magenta]{fingerprint}[/]")

        # Step 3: Query BlockchainNotary.verify_fingerprint
        with console.status("[bold blue]Querying blockchain notary for cryptographic proof...[/]", spinner="dots"):
            result = notary.verify_fingerprint(fingerprint)

        if result.get("is_valid", False):
            # Valid: Render Green Panel
            verified_text = Text()
            verified_text.append("[OK] Cryptographic fingerprint matches an authentic on-chain notary record.\n\n", style="bold white")
            verified_text.append("Block Timestamp   : ", style="bold white")
            verified_text.append(f"{result['timestamp']}\n", style="bold green")
            verified_text.append("Submitter Address : ", style="bold white")
            verified_text.append(f"{result['submitter']}\n", style="bold yellow")
            verified_text.append("Metadata Link     : ", style="bold white")
            verified_text.append(f"{result['metadata_uri']}\n", style="underline blue")
            verified_text.append("Blockchain Network: ", style="bold white")
            verified_text.append(f"{result['network']}\n", style="cyan")
            if result.get("block_number"):
                verified_text.append("Block Recorded    : ", style="bold white")
                verified_text.append(f"#{result['block_number']}", style="bold cyan")

            console.print(
                Panel(
                    verified_text,
                    title="[bold green] INTEGRITY VERIFIED [/]",
                    border_style="bold green",
                    box=box.ROUNDED,
                    padding=(1, 2),
                )
            )
        else:
            # Invalid: Render Red Panel
            tamper_text = Text()
            tamper_text.append("[X] NO VALID NOTARY RECORD FOUND ON-CHAIN\n\n", style="bold white")
            tamper_text.append("Warning: The provided image, social post URL, or platform metadata does not match\n", style="yellow")
            tamper_text.append("any notarized entry. The image, URL, or platform metadata has been altered or never recorded.", style="yellow")

            console.print(
                Panel(
                    tamper_text,
                    title="[bold red] TAMPER ALERT / RECORD NOT FOUND [/]",
                    border_style="bold red",
                    box=box.ROUNDED,
                    padding=(1, 2),
                )
            )

    except InvalidImageError as e:
        print_error_alert("INVALID IMAGE INPUT", str(e), "Verify the image file path and format.")
        sys.exit(1)
    except NoFaceDetectedError as e:
        print_error_alert("NO FACE DETECTED", str(e), "Provide an image with a visible, unobstructed frontal face portrait.")
        sys.exit(1)
    except FaceProcessingError as e:
        print_error_alert("FACE PROCESSING ERROR", str(e), "Check image quality or format.")
        sys.exit(1)
    except RPCConnectionError as e:
        print_error_alert("RPC NODE UNREACHABLE", str(e), "Ensure RPC_URL points to an active EVM node or testnet provider.")
        sys.exit(1)
    except ContractExecutionError as e:
        print_error_alert("SMART CONTRACT ERROR", str(e), "Verify contract state and parameters.")
        sys.exit(1)
    except BlockchainNotaryError as e:
        print_error_alert("BLOCKCHAIN NOTARY ERROR", str(e), "Review your blockchain query parameters.")
        sys.exit(1)
    except Exception as e:
        print_error_alert("UNEXPECTED SYSTEM ERROR", str(e), "Check system logs or contact support.")
        sys.exit(1)


if __name__ == "__main__":
    cli()

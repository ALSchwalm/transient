#!/usr/bin/env python
"""This script embeds the contents of a file into a markdown document
"""
import argparse
import sys


def _parse_args() -> argparse.Namespace:
    """Parse the arguments given on the command line
    """
    arg_parser = argparse.ArgumentParser()

    arg_parser.add_argument(
        "--file-to-embed",
        "-f",
        required=True,
        type=str,
        help="path to the file to be embedded into the markdown document",
    )
    arg_parser.add_argument(
        "--markdown-template",
        "-m",
        required=True,
        type=str,
        help="path to the markdown document template",
    )
    arg_parser.add_argument(
        "--output-file",
        "-o",
        required=True,
        type=str,
        help="path to output the generated markdown document",
    )

    return arg_parser.parse_args()


def _write_markdown_document_to_file(
    markdown_document: str, output_file_path: str
) -> None:
    """Writes the markdown document to the output file path
    """
    with open(output_file_path, "w") as output_file:
        output_file.write(markdown_document)


def _read_file_to_string(file_path: str) -> str:
    """Returns the contents of the given file as a string
    """
    with open(file_path) as file:
        contents = file.read()

    return contents


def embed_file_contents_into_markdown_document(
    file_to_embed_path: str, markdown_template_path: str, output_file_path: str
) -> None:
    """Embeds the given file into the markdown template, generating a markdown
       document.

       Note that the markdown template must contain the replacement field:
           {EMBED_FILE_HERE}
    """
    file_to_embed = _read_file_to_string(file_to_embed_path)
    markdown_template = _read_file_to_string(markdown_template_path)

    markdown_document = markdown_template.format(EMBED_FILE_HERE=file_to_embed)

    _write_markdown_document_to_file(markdown_document, output_file_path)


if __name__ == "__main__":

    args = _parse_args()

    try:
        embed_file_contents_into_markdown_document(
            args.file_to_embed, args.markdown_template, args.output_file
        )
    except (FileNotFoundError, PermissionError) as error:
        print(error)
        sys.exit(-1)
    except KeyError as error:
        print(
            f'The replacement field "{{EMBED_FILE_HERE}}" was not found in {args.markdown_template}'
        )
        sys.exit(-1)

    sys.exit(0)

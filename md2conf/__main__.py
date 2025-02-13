"""
Publish Markdown files to Confluence wiki.

Parses Markdown files, converts Markdown content into the Confluence Storage Format (XHTML), and invokes
Confluence API endpoints to upload images and content.

Copyright 2022-2025, Levente Hunyadi

:see: https://github.com/hunyadi/md2conf
"""

import argparse
import logging
import os.path
import sys
import typing
from pathlib import Path
from typing import Any, Literal, Optional, Sequence, Union

import requests

from . import __version__
from .api import ConfluenceAPI
from .application import Application
from .converter import ConfluenceDocumentOptions
from .processor import Processor
from .properties import ConfluenceProperties


class Arguments(argparse.Namespace):
    mdpath: Path
    domain: str
    path: str
    username: str
    apikey: str
    space: str
    loglevel: str
    ignore_invalid_url: bool
    heading_anchors: bool
    root_page: Optional[str]
    generated_by: Optional[str]
    render_mermaid: bool
    diagram_output_format: Literal["png", "svg"]
    local: bool
    headers: dict[str, str]
    webui_links: bool


class KwargsAppendAction(argparse.Action):
    """Append key-value pairs to a dictionary"""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Union[None, str, Sequence[Any]],
        option_string: Optional[str] = None,
    ) -> None:
        try:
            d = dict(map(lambda x: x.split("="), typing.cast(Sequence[str], values)))
        except ValueError:
            raise argparse.ArgumentError(
                self,
                f'Could not parse argument "{values}". It should follow the format: k1=v1 k2=v2 ...',
            )
        setattr(namespace, self.dest, d)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.prog = os.path.basename(os.path.dirname(__file__))
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "mdpath", help="Path to Markdown file or directory to convert and publish."
    )
    parser.add_argument("-d", "--domain", help="Confluence organization domain.")
    parser.add_argument(
        "-p", "--path", help="Base path for Confluence (default: '/wiki/')."
    )
    parser.add_argument("-u", "--username", help="Confluence user name.")
    parser.add_argument(
        "-a",
        "--apikey",
        help="Confluence API key. Refer to documentation how to obtain one.",
    )
    parser.add_argument(
        "-s",
        "--space",
        help="Confluence space key for pages to be published. If omitted, will default to user space.",
    )
    parser.add_argument(
        "-l",
        "--loglevel",
        choices=[
            logging.getLevelName(level).lower()
            for level in (
                logging.DEBUG,
                logging.INFO,
                logging.WARN,
                logging.ERROR,
                logging.CRITICAL,
            )
        ],
        default=logging.getLevelName(logging.INFO),
        help="Use this option to set the log verbosity.",
    )
    parser.add_argument(
        "-r",
        dest="root_page",
        help="Root Confluence page to create new pages. If omitted, will raise exception when creating new pages.",
    )
    parser.add_argument(
        "--generated-by",
        default="This page has been generated with a tool.",
        help="Add prompt to pages (default: 'This page has been generated with a tool.').",
    )
    parser.add_argument(
        "--no-generated-by",
        dest="generated_by",
        action="store_const",
        const=None,
        help="Do not add 'generated by a tool' prompt to pages.",
    )
    parser.add_argument(
        "--render-mermaid",
        dest="render_mermaid",
        action="store_true",
        default=True,
        help="Render Mermaid diagrams as image files and add as attachments.",
    )
    parser.add_argument(
        "--no-render-mermaid",
        dest="render_mermaid",
        action="store_false",
        help="Inline Mermaid diagram in Confluence page.",
    )
    parser.add_argument(
        "--render-mermaid-format",
        dest="diagram_output_format",
        choices=["png", "svg"],
        default="png",
        help="Format for rendering Mermaid diagrams (default: 'png').",
    )
    parser.add_argument(
        "--heading-anchors",
        action="store_true",
        default=False,
        help="Place an anchor at each section heading with GitHub-style same-page identifiers.",
    )
    parser.add_argument(
        "--ignore-invalid-url",
        action="store_true",
        default=False,
        help="Emit a warning but otherwise ignore relative URLs that point to ill-specified locations.",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        default=False,
        help="Write XHTML-based Confluence Storage Format files locally without invoking Confluence API.",
    )
    parser.add_argument(
        "--headers",
        nargs="*",
        required=False,
        action=KwargsAppendAction,
        metavar="KEY=VALUE",
        help="Apply custom headers to all Confluence API requests.",
    )
    parser.add_argument(
        "--webui-links",
        action="store_true",
        default=False,
        help="Enable Confluence Web UI links. (Typically required for on-prem versions of Confluence.)",
    )

    args = Arguments()
    parser.parse_args(namespace=args)

    args.mdpath = Path(args.mdpath)

    logging.basicConfig(
        level=getattr(logging, args.loglevel.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(funcName)s [%(lineno)d] - %(message)s",
    )

    options = ConfluenceDocumentOptions(
        heading_anchors=args.heading_anchors,
        ignore_invalid_url=args.ignore_invalid_url,
        generated_by=args.generated_by,
        root_page_id=args.root_page,
        render_mermaid=args.render_mermaid,
        diagram_output_format=args.diagram_output_format,
        webui_links=args.webui_links,
    )
    properties = ConfluenceProperties(
        args.domain, args.path, args.username, args.apikey, args.space, args.headers
    )
    if args.local:
        Processor(options, properties).process(args.mdpath)
    else:
        try:
            with ConfluenceAPI(properties) as api:
                Application(
                    api,
                    options,
                ).synchronize(args.mdpath)
        except requests.exceptions.HTTPError as err:
            logging.error(err)

            # print details for a response with JSON body
            if err.response is not None:
                try:
                    logging.error(err.response.json())
                except requests.exceptions.JSONDecodeError:
                    pass

            sys.exit(1)


if __name__ == "__main__":
    main()

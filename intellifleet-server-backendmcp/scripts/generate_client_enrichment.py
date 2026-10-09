"""Export deterministic enrichment from the authoritative workbook only."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.client_network import configuration, generate, summary

parser=argparse.ArgumentParser()
parser.add_argument('--seed',type=int)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
config=configuration()
if args.seed is not None:config=replace(config,seed=args.seed)
model=generate(config=config)
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(model,indent=2))
print(json.dumps(summary(model),indent=2))

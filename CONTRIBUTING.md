# Contributing

This repo is primarily a personal testing and reference workspace, but the same conventions help keep it easy to navigate and safe to extend.

## Purpose

- Keep examples runnable.
- Keep examples small enough to understand in one sitting.
- Prefer clear patterns over overly clever abstractions.

## Repo Conventions

- Add new topic areas as separate folders when they teach a distinct concept.
- Give each topic folder a `README.md` and a runnable example script.
- Keep route handlers thin and move real rules into services or helpers.
- Keep schemas, services, repositories, and operational concerns visibly separated.
- If an example intentionally simplifies production reality, say so in the README.

## Naming

- Use descriptive snake_case Python filenames.
- Use numbered folders in tutorial flows so the order stays obvious.
- Keep README titles aligned with the folder topic.

## Testing Expectations

- Each runnable example should have either self-tests or demo output.
- Prefer lightweight verification that works with `python3` alone.
- If a new example introduces shared behavior, add a test path for it.

## Documentation Expectations

- Link related topics so readers can move through the repo naturally.
- Include a short "when to use this" explanation in topic READMEs.
- Call out learning shortcuts versus production recommendations.

## Practical Notes

- `rest_api_examples` uses import-friendly naming so scripts and tooling can reference it consistently.
- `make verify` is the quickest way to confirm the example set still runs cleanly.

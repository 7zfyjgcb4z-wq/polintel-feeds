import asyncio
import logging
import sys

import click
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


@click.group()
def cli():
    """Pol-Intel UK job scraper."""


@cli.command()
@click.option("--country", default="uk", show_default=True, help="Country filter.")
@click.option("--source", "sources", multiple=True, help="Run only named source(s).")
@click.option("--skip-ai", is_flag=True, help="Skip Tier 2 generic AI scrapers.")
@click.option("--dry-run", is_flag=True, help="Fetch + clean HTML but do not call Claude API.")
@click.option("--db", "db_path", default="data/jobs.db", show_default=True)
@click.option("--output", "output_dir", default="feeds/", show_default=True)
def run(country, sources, skip_ai, dry_run, db_path, output_dir):
    """Run the full scraping pipeline."""
    from src.pipeline import run_pipeline

    result = asyncio.run(
        run_pipeline(
            country=country,
            sources=list(sources) or None,
            skip_ai=skip_ai,
            dry_run=dry_run,
            db_path=db_path,
            output_dir=output_dir,
        )
    )
    click.echo(
        f"Done: {result['total']} scraped, {result['new']} new, "
        f"{result['active']} active in DB."
    )
    if result["failed"]:
        click.echo(f"Failed sources: {', '.join(result['failed'])}", err=True)


@cli.command()
@click.option("--db", "db_path", default="data/jobs.db", show_default=True)
@click.option("--output", "output_dir", default="feeds/", show_default=True)
@click.option("--country", default="uk", show_default=True)
def feeds(db_path, output_dir, country):
    """Regenerate RSS feeds from the database (no scraping)."""
    from src.db.store import JobStore
    from src.feed.generator import generate_feeds, generate_status

    db = JobStore(db_path)
    jobs = db.get_active_jobs(country=country)
    counts = generate_feeds(jobs, output_dir=output_dir)
    generate_status(output_dir=output_dir, total_active_jobs=len(jobs), feeds_generated=len(counts))
    db.close()
    click.echo(f"Generated {len(counts)} feeds from {len(jobs)} active jobs.")
    for cat, n in counts.items():
        click.echo(f"  uk-{cat}.xml: {n} jobs")


@cli.command()
@click.option("--config", "config_path", default="src/config/sources.yaml", show_default=True)
def sources(config_path):
    """List all configured sources."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    rows = config.get("sources", [])
    click.echo(f"{'Name':<40} {'Tier':<10} {'Category':<25} {'Enabled'}")
    click.echo("-" * 85)
    for s in rows:
        tier = s.get("scraper", "?")
        enabled = "yes" if s.get("enabled", True) else "no"
        click.echo(f"{s['name']:<40} {tier:<10} {s.get('category',''):<25} {enabled}")
    click.echo(f"\nTotal: {len(rows)} sources")


@cli.command()
@click.option("--source", "source_name", required=True, help="Source name to test.")
@click.option("--dry-run/--no-dry-run", default=False, show_default=True,
              help="For generic sources: fetch + clean but skip API call.")
@click.option("--config", "config_path", default="src/config/sources.yaml", show_default=True)
def test(source_name, dry_run, config_path):
    """Test a single source — print jobs, no DB write."""
    from src.pipeline import load_config, load_dedicated_scraper

    config = load_config(config_path)
    matches = [s for s in config["sources"] if s["name"] == source_name]
    if not matches:
        click.echo(f"Source '{source_name}' not found.", err=True)
        sys.exit(1)

    source = matches[0]
    tier = source.get("scraper")

    if tier == "dedicated":

        async def _run_dedicated():
            scraper = load_dedicated_scraper(source)
            return await scraper.scrape()

        jobs = asyncio.run(_run_dedicated())

    elif tier == "generic":
        from src.db.store import JobStore
        from src.scrapers.generic import generic_scrape

        async def _run_generic():
            db = JobStore(":memory:")
            jobs = await generic_scrape(source, db, dry_run=dry_run)
            db.close()
            return jobs

        if dry_run:
            click.echo(f"[DRY RUN] Fetching {source['url']} — Claude API will NOT be called.")
        jobs = asyncio.run(_run_generic())

    else:
        click.echo(f"Unknown scraper type '{tier}' for source '{source_name}'.", err=True)
        sys.exit(1)

    if not jobs:
        click.echo(f"No jobs returned from '{source_name}' (dry-run or page unchanged).")
        return

    click.echo(f"\n{len(jobs)} jobs from '{source_name}':")
    for job in jobs:
        click.echo(f"  [{job.category}] {job.title} — {job.organisation}")
        click.echo(f"    {job.url}")
        if job.description:
            click.echo(f"    {job.description[:120]}...")
        click.echo()


if __name__ == "__main__":
    cli()

-- rss_sources registration for the internship_graduate pipeline feeds.
-- Apply to Supabase project cnyjrdbbzvidcbtrwacq AFTER the first build
-- that emits these files to GitHub Pages.
-- All feeds start disabled (is_enabled = false) matching the source gate.
-- Enable each feed entry when the corresponding source is enabled in
-- sources-internship-graduate.yaml and ATS extractor Part 1 is verified.
--
-- Base URL: https://7zfyjgcb4z-wq.github.io/polintel-feeds
-- source_label pattern: "Pol-Intel: Early Careers — <Category>"
-- The `source` column in jobs receives this value — it is the provenance carrier.
-- fetch-rss recognises these as Pol-Intel sources (url contains 'github.io')
-- and sets description_source='scraper', skipping blocklist and relevance filter.

INSERT INTO public.rss_sources (name, url, source_label, is_enabled) VALUES
  (
    'Pol-Intel Early Careers — Public Affairs',
    'https://7zfyjgcb4z-wq.github.io/polintel-feeds/internship_graduate-public-affairs.xml',
    'Pol-Intel: Early Careers — Public Affairs',
    false
  ),
  (
    'Pol-Intel Early Careers — Research & Polling',
    'https://7zfyjgcb4z-wq.github.io/polintel-feeds/internship_graduate-research.xml',
    'Pol-Intel: Early Careers — Research',
    false
  ),
  (
    'Pol-Intel Early Careers — International Organisations',
    'https://7zfyjgcb4z-wq.github.io/polintel-feeds/internship_graduate-international-orgs.xml',
    'Pol-Intel: Early Careers — International Orgs',
    false
  ),
  (
    'Pol-Intel Early Careers — US Fellowships',
    'https://7zfyjgcb4z-wq.github.io/polintel-feeds/internship_graduate-us-fellowships.xml',
    'Pol-Intel: Early Careers — US Fellowships',
    false
  ),
  (
    'Pol-Intel Early Careers — US Campaigns',
    'https://7zfyjgcb4z-wq.github.io/polintel-feeds/internship_graduate-us-campaigns.xml',
    'Pol-Intel: Early Careers — US Campaigns',
    false
  ),
  (
    'Pol-Intel Early Careers — US Congress',
    'https://7zfyjgcb4z-wq.github.io/polintel-feeds/internship_graduate-us-congress.xml',
    'Pol-Intel: Early Careers — US Congress',
    false
  ),
  (
    'Pol-Intel Early Careers — General',
    'https://7zfyjgcb4z-wq.github.io/polintel-feeds/internship_graduate-general.xml',
    'Pol-Intel: Early Careers — General',
    false
  );

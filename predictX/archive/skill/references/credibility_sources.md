# PDX Credibility Sources

Reference document for the credibility scoring system used in evidence evaluation.

## Tier 1: High Credibility (8-10)

| Source | Score | Domain |
|--------|-------|--------|
| Nature | 10 | Science |
| Science (AAAS) | 10 | Science |
| The Lancet | 10 | Medicine |
| NEJM | 10 | Medicine |
| IEEE | 9 | Technology |
| ACM | 9 | Computer Science |
| Reuters | 9 | News |
| Associated Press | 9 | News |
| WHO | 9 | Health |
| CDC | 9 | Health |
| World Bank | 9 | Economics |
| IMF | 9 | Economics |
| arXiv | 8 | Preprints |
| SSRN | 8 | Social Science |
| BBC | 8 | News |
| NPR | 8 | News |
| Wall Street Journal | 8 | Finance/News |
| Financial Times | 8 | Finance |
| Bloomberg | 8 | Finance |
| FDA | 8 | Health/Regulation |

## Tier 2: Moderate Credibility (5-7)

| Source | Score | Domain |
|--------|-------|--------|
| Wikipedia | 7 | General |
| New York Times | 7 | News |
| Washington Post | 7 | News |
| The Guardian | 7 | News |
| Economist | 7 | Economics |
| TechCrunch | 6 | Technology |
| Ars Technica | 6 | Technology |
| Wired | 6 | Technology |
| CNBC | 6 | Finance |
| Forbes | 6 | Business |
| Snopes | 6 | Fact-checking |
| PolitiFact | 6 | Fact-checking |
| GitHub | 5 | Technology |
| Stack Overflow | 5 | Technology |

## Tier 3: Lower Credibility (1-4)

| Source | Score | Domain |
|--------|-------|--------|
| Reddit | 4 | Social |
| Twitter/X | 3 | Social |
| YouTube | 3 | Video |
| Medium | 3 | Blog |
| Substack | 3 | Blog |
| Quora | 2 | Q&A |
| Facebook | 2 | Social |
| TikTok | 1 | Social |
| Unknown/Other | 3 | Default |

## Scoring Methodology

The credibility score contributes to the **Authenticity** dimension (0-25 points) of evidence evaluation:

- `authenticity_score = (credibility / 10) * 25`
- Sources not in the database default to score 3
- Subdomain matching: `news.bbc.co.uk` matches `bbc.co.uk`

## Updating Sources

To add new sources, update `engine/credibility_db.py` with:
1. Domain name (lowercase, without www prefix)
2. Credibility score (1-10)
3. Brief justification for the score

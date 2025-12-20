import csv
import time
import sys
import re
from collections import defaultdict
from pyalex import Authors, Works, config

# Configuration
config.email = "your-email@university.edu"  # Set your email for polite pool
config.max_retries = 3
config.retry_backoff_factor = 0.1
config.retry_http_codes = [429, 500, 503]

PAUSE = 1.0  # Pause between processing authors

def norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()

def get_author_id(name: str) -> str:
    """Get OpenAlex ID from author name using PyAlex"""
    try:
        results = Authors().search(name).get()
        if not results:
            raise ValueError(f"No OpenAlex author found for: {name}")
        return results[0]["id"]
    except Exception as e:
        raise RuntimeError(f"Error finding author {name}: {str(e)}")

def fetch_author_works(author_url: str):
    """Fetch all works for an author using PyAlex (with venue fields)."""
    try:
        fields = [
            "id", "display_name", "title", "doi",
            "cited_by_count", "cited_by_api_url", "publication_year",
            "primary_location", "locations", "biblio", "authorships"
        ]
        # one page (fast); switch to paginate() if you want truly ALL works
        works = (
            Works()
            .filter(author={"id": author_url})
            .select(fields)
            .get(per_page=200)
        )
        return works
    except Exception as e:
        print(f"⚠️ Error fetching works for {author_url}: {str(e)}")
        return []


def main(researchers_list: list[tuple]):
    # Sets for deduplication
    R, W, V, WV, A, INST, AI = set(), set(), set(), set(), set(), set(), set()
    # Dictionary to track co-author relationships
    coauthor_relationships = defaultdict(lambda: defaultdict(int))

    with open("researchers_openalex.csv", "w", newline="", encoding="utf-8") as fr, \
         open("publications.csv", "w", newline="", encoding="utf-8") as fw, \
         open("venues.csv", "w", newline="", encoding="utf-8") as fv, \
         open("publication_venue.csv", "w", newline="", encoding="utf-8") as fwv, \
         open("authorship.csv", "w", newline="", encoding="utf-8") as fa, \
         open("coauthor_relationships.csv", "w", newline="", encoding="utf-8") as fcr, \
         open("institutions.csv", "w", newline="", encoding="utf-8") as fi, \
         open("author_institution.csv", "w", newline="", encoding="utf-8") as fai:

        wr = csv.writer(fr)
        wr.writerow(["openalex_url", "name", "normalized_name"])
        
        ww = csv.writer(fw)
        ww.writerow(["openalex_url", "doi", "title", "cited_by_count", "cited_by_url", "publication_year"])
        
        wv = csv.writer(fv)
        wv.writerow(["name", "type", "volume", "page", "pub_openalex_url"])
        
        wwv = csv.writer(fwv)
        wwv.writerow(["publication_openalex_url", "venue_name", "venue_type"])
        
        wa = csv.writer(fa)
        wa.writerow(["publication_openalex_url", "researcher_openalex_url"])
        
        wcr = csv.writer(fcr)
        wcr.writerow(["researcher1_openalex_url", "researcher2_openalex_url", "collaboration_count"])

       # institutions.csv — one row per institution
        wi = csv.writer(fi)
        wi.writerow(["openalex_url", "name", "ror", "country_code"])

        # author_institution.csv — a link table: work x author x institution
        wai = csv.writer(fai)
        wai.writerow(["publication_openalex_url", "author_openalex_url", "institution_openalex_url"])

        total = len(researchers_list)
        for idx, (name, openalex_url) in enumerate(researchers_list, 1):
            print(f"Processing {idx}/{total}: {name}")
            
            # Skip if we've already processed this researcher
            if openalex_url and any(r[0] == openalex_url for r in R):
                print(f"  Skipping {name} - already processed")
                continue
                
            if openalex_url:
                author_url = openalex_url
                normalized_name = norm_name(name)
                key = (author_url, name, normalized_name)
                if key not in R:
                    wr.writerow([author_url, name, normalized_name])
                    R.add(key)
            else:
                try:
                    author_url = get_author_id(name)
                    normalized_name = norm_name(name)
                    key = (author_url, name, normalized_name)
                    if key not in R:
                        wr.writerow([author_url, name, normalized_name])
                        R.add(key)
                except Exception as e:
                    print(f"Skipping {name} due to error: {e}")
                    continue

            # Fetch works for this author
            try:
                works = fetch_author_works(author_url)
                works_count = len(works)
                
                for w in works:
                    work_url = w.get("id", "")
                    title = w.get("title") or w.get("display_name", "")
                    doi = w.get("doi", "")
                    year = w.get("publication_year", "")
                    cited_by_count = w.get("cited_by_count", 0)
                    cited_by_url = w.get("cited_by_api_url", "")

                    # Write to publications.csv
                    keyw = (work_url, doi, title, cited_by_count, cited_by_url, year)
                    if keyw not in W:
                        ww.writerow([work_url, doi, title, cited_by_count, cited_by_url, year])
                        W.add(keyw)

                    # Handle venue data (prefer primary_location.source, fallback to locations[].source)
                    primary = w.get("primary_location") or {}
                    src = primary.get("source") or {}

                    venue_name = (src.get("display_name") or "").strip()
                    venue_type = (src.get("type") or "").strip()   # e.g., 'journal', 'conference', 'repository', ...

                    # Fallback: scan other locations if primary is missing/empty
                    if not venue_name:
                        for loc in (w.get("locations") or []):
                            s = (loc.get("source") or {})
                            if s.get("display_name"):
                                venue_name = (s.get("display_name") or "").strip()
                                venue_type = (s.get("type") or venue_type or "").strip()
                                break

                    # Only if still empty, mark as Other
                    venue_type = venue_type if venue_type else "Other"

                    # Volume / pages come from biblio
                    biblio = w.get("biblio") or {}
                    volume = (biblio.get("volume") or "").strip()
                    first_page = (biblio.get("first_page") or "").strip()
                    last_page  = (biblio.get("last_page") or "").strip()
                    page = f"{first_page}–{last_page}".strip("– ")
                    pub_openalex_url = w.get("id", "")
                    
                    # Always write venue data if we have a venue name
                    if venue_name:
                        # Write to venues.csv
                        keyv = (venue_name, venue_type, volume, page)
                        if keyv not in V:
                            wv.writerow([venue_name, venue_type, volume, page, pub_openalex_url])
                            V.add(keyv)
                        
                        # Write to publication_venue.csv
                        keywv = (work_url, venue_name, venue_type)
                        if keywv not in WV:
                            wwv.writerow([work_url, venue_name, venue_type])
                            WV.add(keywv)
                    else:
                        print(f"  No venue found for publication: {title}")

                    # Handle authorships and track co-author relationships
                    authors_in_work = []
                    for au in w.get("authorships", []):
                        author_info = au.get("author") or {}
                        a_id   = (author_info.get("id") or "").strip()
                        a_name = (author_info.get("display_name") or "").strip()

                        if not a_id:
                            continue

                        authors_in_work.append(a_id)

                        # Add co-author to researchers_openalex.csv
                        if a_name:
                            normalized_author_name = norm_name(a_name)
                            keyr = (a_id, a_name, normalized_author_name)
                            if keyr not in R:
                                wr.writerow([a_id, a_name, normalized_author_name])
                                R.add(keyr)

                        # Write to authorship.csv (work ↔ author)
                        keya = (work_url, a_id)
                        if keya not in A:
                            wa.writerow([work_url, a_id])
                            A.add(keya)

                        # --- institutions for this authorship (must come AFTER a_id is set) ---
                        for inst in au.get("institutions", []):
                            inst_id   = (inst.get("id") or "").strip()                 # e.g. https://openalex.org/I123...
                            inst_name = (inst.get("display_name") or "").strip()
                            ror       = (inst.get("ror") or "").strip()
                            country   = (inst.get("country_code") or "").strip()

                            # Dedup institutions file
                            if inst_id:
                                keyi = (inst_id, inst_name, ror, country)
                                if keyi not in INST:
                                    wi.writerow([inst_id, inst_name, ror, country])
                                    INST.add(keyi)

                                # Link work+author to institution
                                key_ai = (work_url, a_id, inst_id)
                                if key_ai not in AI:
                                    wai.writerow([work_url, a_id, inst_id])
                                    AI.add(key_ai)

                    
                    # Track co-author relationships for all pairs of authors in this work
                    for i in range(len(authors_in_work)):
                        for j in range(i + 1, len(authors_in_work)):
                            author1 = authors_in_work[i]
                            author2 = authors_in_work[j]
                            # Ensure consistent ordering to avoid duplicates
                            if author1 < author2:
                                coauthor_relationships[author1][author2] += 1
                            else:
                                coauthor_relationships[author2][author1] += 1
                
                print(f"  Found {works_count} works for {name}")
                
            except Exception as e:
                print(f"Error processing works for {author_url}: {e}")
                continue
            
            # Pause between authors to avoid rate limiting
            if idx < total:
                print(f"Waiting {PAUSE:.1f} seconds before next author...")
                time.sleep(PAUSE)
        
        # Write co-author relationships to CSV
        for author1 in coauthor_relationships:
            for author2 in coauthor_relationships[author1]:
                count = coauthor_relationships[author1][author2]
                wcr.writerow([author1, author2, count])

        print("CSV files have been successfully created with all data!")

if __name__ == "__main__":
    # IMPORTANT: Replace with your actual email
    config.email = "your-email@university.edu"
    
    researchers = []
    try:
        with open('sys_users.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                first_name = row.get('first_name', '')
                last_name = row.get('last_name', '')
                name = f"{first_name} {last_name}".strip()
                openalex_url = row.get('authorID', '').strip()
                if openalex_url:
                    researchers.append((name, openalex_url))
                else:
                    researchers.append((name, None))
    except FileNotFoundError:
        print("sys_users.csv not found. Using hardcoded list.")
        # Fallback to hardcoded list if sys_users.csv is not available
        researchers = [
            ("Petr Musilek", None),
            ("Behrooz Nowrouzian", None),
            ("Yang Liu", None),
            # Add other researchers as needed
        ]

    print(f"Starting to process {len(researchers)} researchers")
    main(researchers)
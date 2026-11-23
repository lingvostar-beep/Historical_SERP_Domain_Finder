export type SerpWindow = {
  provider_primary: string
  max_history_days: number
  earliest_allowed_date: string
  today: string
  reference_price_per_snapshot_usd: number
  concurrency: number
  note: string
}

export type ProjectListItem = {
  id: string
  name: string
  owner_id: string | null
  keywords: number
  targets: number
  runs: number
  created_at: string | null
}

export type LocationLang = {
  language_name: string
  language_code: string
}

export type LocationItem = {
  location_code: number
  location_name: string
  country_iso_code: string | null
  location_type: string | null
  languages: LocationLang[]
}

export type Target = {
  location_code: number
  location_name: string
  language_code: string
}

export type RunProgress = {
  run_id: string
  status: string
  spent_usd: string
  budget_cap: string
  budget_ratio?: number
  budget_warning_80?: boolean
  budget_headroom_usd?: string
  next_query_projected_usd?: string
  can_afford_next_query?: boolean
  depth: number
  source: string
  date_from: string
  date_to: string
  queries_total: number
  queries_by_status: Record<string, number>
  snapshots: number
  planned_months: number
}

export type DomainRow = {
  domain: string
  keywords_found: number
  countries_found: number
  months_found: number
  serp_appearances: number
  best_organic_rank: number | null
  first_seen: string | null
  last_seen: string | null
  best_rank_keyword: string | null
  sample_url: string | null
  registration_status?: string | null
  eligibility_status?: string | null
  availability_provider?: string | null
  last_checked_at?: string | null
  check_age?: string | null
  registration_restrictions?: string | null
  confirmation_status?: string | null
}

export type PositionRow = {
  keyword: string
  location_code: number
  location_name: string | null
  language: string
  observed_at: string | null
  month: string
  organic_rank: number | null
  absolute_rank: number | null
  domain: string | null
  hostname: string | null
  url: string | null
  title: string | null
  source: string | null
}

export type CoverageRow = {
  keyword: string
  location_code: number
  language: string
  month: string
  status: string
  snapshot_count: number
  organic_count: number
}

export type PositionFacets = {
  locations: { location_code: number; location_name: string; language_code: string }[]
  languages: string[]
  months: string[]
  sources: string[]
  rank_presets: number[]
}

export type PositionsPage = PageResult<PositionRow> & { facets?: PositionFacets }

export type CoverageMatrix = {
  months: string[]
  locations: { location_code: number; location_name: string | null }[]
  blocks: {
    keyword: string
    rows: {
      location_code: number
      location_name: string | null
      cells: Record<string, string | undefined>
    }[]
  }[]
  keyword_total: number
  keyword_page: number
  keyword_page_size: number
  stats: {
    planned_snapshots: number
    available_snapshots: number
    status_counts: Record<string, number>
  }
  note?: string
}

export type AvailabilityRow = DomainRow & {
  registration_status: string | null
  eligibility_status: string | null
}

export type JobProgress = {
  job_id: string
  run_id: string
  status: string
  provider: string
  spent_credits: number
  budget_cap_credits: number
  spent_usd: string
  budget_cap_usd: string
  force_refresh: boolean
  items_by_status: Record<string, number>
}

export type PageResult<T> = {
  total: number
  page: number
  page_size: number
  items: T[]
}

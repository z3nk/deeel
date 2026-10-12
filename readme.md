# GIVE ME THE DEEEEEEEEEL

Basic scaffold for a student-focused meal-deal finder web app.

## Project Structure

```text
.
├── apps
│   ├── api
│   │   └── src
│   │       ├── models
│   │       ├── routes
│   │       ├── services
│   │       └── utils
│   └── web
│       ├── public
│       └── src
│           ├── components
│           ├── pages
│           ├── styles
│           └── utils
├── data
│   ├── indexed
│   └── raw
├── docs
└── shared
    └── types
```

## Notes

- `apps/web` will contain the student-facing web app.
- `apps/api` will contain ingestion/indexing/search APIs.
- `shared/types` is for shared contracts between frontend and backend.
- `data` is for local raw and indexed dataset snapshots.

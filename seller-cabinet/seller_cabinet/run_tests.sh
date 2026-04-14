
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

COMPOSE=(docker compose -f docker-compose.test.yml)

"${COMPOSE[@]}" build tests
"${COMPOSE[@]}" run --rm tests

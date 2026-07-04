from fastapi import Response


def set_shared_cache_header(response: Response, *, s_maxage: int, stale_while_revalidate: int) -> None:
    response.headers["Cache-Control"] = (
        f"public, max-age=0, s-maxage={s_maxage}, stale-while-revalidate={stale_while_revalidate}"
    )

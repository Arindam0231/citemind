import json
import hashlib
import logging
from typing import List, Dict, Any, Optional
import os
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_anthropic import ChatAnthropic
from ollama import chat

import re

logger = logging.getLogger(__name__)

cache: Dict[str, Any] = {}


def is_safe_code(code: str) -> bool:
    """Basic safety check for generated code."""
    forbidden = ["os.system", "subprocess", "eval", "shutil"]
    for f in forbidden:
        if f in code:
            return False
    return True


def _extract_json(raw: Any) -> Any:
    """
    Strip markdown fences, find JSON structures { } or [ ], and parse.
    If input is not a string, returns as is.
    """
    if not isinstance(raw, str):
        return raw

    if not raw or not raw.strip():
        return raw

    text = raw.strip()

    # 1. Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Try to find the first '{' or '[' and last '}' or ']'
    # Using regex to find the largest span starting with { or [ and ending with } or ]
    match = re.search(r"([\[{][\s\S]*[\]}])", text)
    if match:
        json_str = match.group(1).strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    # 3. Fallback: try stripping markdown code blocks if the above failed
    # (though re.search should have caught it)
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return raw


LANGCHAIN_ROLE_MAP = {
    "human": "user",
    "ai": "assistant",
    "system": "system",
    "tool": "tool",
}


def _to_ollama_messages(messages: list) -> list[dict]:
    result = []
    for m in messages:
        # Already a plain dict (e.g. {"role": ..., "content": ...})
        if isinstance(m, dict):
            if "role" in m:
                result.append(m)
            elif "type" in m:
                result.append(
                    {
                        "role": LANGCHAIN_ROLE_MAP.get(m["type"], m["type"]),
                        "content": m.get("content", ""),
                    }
                )
        # LangChain BaseMessage subclass
        else:
            role = LANGCHAIN_ROLE_MAP.get(m.type, m.type)
            result.append({"role": role, "content": m.content})
    return result


def llm_service(messages: List[BaseMessage], use_cache: bool = False) -> dict | str:
    print("LLM Service called with messages:")
    for msg in messages:
        print(f"  {msg.type}: {msg.content}")

    logger.debug(
        "llm_service | invoking LLM",
        extra={
            "message_count": len(messages),
            "last_message_role": (
                getattr(messages[-1], "type", "unknown") if messages else None
            ),
            "last_message_preview": (
                str(messages[-1].content)[:200] if messages else None
            ),
        },
    )

    if use_cache:
        cache_key = hashlib.md5(
            json.dumps(
                [{"role": m.type, "content": str(m.content)} for m in messages],
                sort_keys=True,
            ).encode()
        ).hexdigest()

        if cache_key in cache:
            logger.debug("llm_service | cache hit | key=%s", cache_key)
            return cache[cache_key]

    try:
        response = chat(
            model="qwen3.5",
            messages=_to_ollama_messages(messages),
        ).message
        logger.debug(
            "llm_service | response received",
            extra={
                "response_preview": str(response.content)[:200],
                "response_type": type(response.content).__name__,
            },
        )
        try:
            cleaned_response_content = _extract_json(response.content)
            result = cleaned_response_content
        except Exception as e:
            logger.warning(
                "llm_service | json.loads failed, returning raw content",
                extra={"error": str(e)},
            )
            result = response.content

        if use_cache:
            cache[cache_key] = result
            logger.debug("llm_service | cache miss | stored key=%s", cache_key)

        return result

    except Exception as e:
        logger.error(
            "llm_service | LLM invocation failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise


def llm_exec_with_retry(
    fn_name: str,
    messages: List[BaseMessage],
    fn_kwargs: Optional[Dict[str, Any]] = None,
    exec_globals: Optional[Dict[str, Any]] = None,
    response_key: str = "response",
    max_retries: int = 3,
) -> Any:
    if fn_kwargs is None:
        fn_kwargs = {}
    if exec_globals is None:
        exec_globals = {}

    conversation: List[BaseMessage] = list(messages)
    last_error: Optional[str] = None
    generated_code: str = ""

    logger.info(
        "llm_exec_with_retry | starting",
        extra={"fn_name": fn_name, "max_retries": max_retries},
    )

    for attempt in range(max_retries + 1):
        logger.debug(
            "llm_exec_with_retry | attempt",
            extra={"fn_name": fn_name, "attempt": attempt + 1, "of": max_retries + 1},
        )

        if attempt > 0 and last_error:
            logger.warning(
                "llm_exec_with_retry | retrying after error",
                extra={
                    "fn_name": fn_name,
                    "attempt": attempt + 1,
                    "last_error": last_error,
                    "failing_code_preview": generated_code[:300],
                },
            )
            conversation.append(
                AIMessage(content=json.dumps({response_key: generated_code}))
            )
            conversation.append(
                HumanMessage(
                    content=(
                        f"Your previous code caused the following error:\n\n"
                        f"{last_error}\n\n"
                        f"Failing code:\n```python\n{generated_code}\n```\n\n"
                        f"Please fix the function and return the corrected JSON "
                        f"in the same format as before."
                    )
                )
            )

        raw_response = llm_service(conversation)

        try:
            parsed = (
                json.loads(raw_response)
                if isinstance(raw_response, str)
                else raw_response
            )
        except json.JSONDecodeError as exc:
            last_error = f"LLM response was not valid JSON: {exc}\nRaw: {raw_response}"
            logger.warning(
                "llm_exec_with_retry | JSON parse failed",
                extra={"fn_name": fn_name, "attempt": attempt + 1, "error": last_error},
            )
            continue
        generated_code = parsed.get(response_key, "")
        reasoning = parsed.get("reasoning", "")
        safety_check = is_safe_code(generated_code)
        if not safety_check:
            last_error = "Generated code failed the safety check."
            logger.warning(
                "llm_exec_with_retry | safety check failed on initial response",
                extra={
                    "fn_name": fn_name,
                    "attempt": attempt + 1,
                    "code_preview": generated_code[:300],
                },
            )
            continue
        logger.debug(
            "llm_exec_with_retry | parsed response",
            extra={
                "fn_name": fn_name,
                "attempt": attempt + 1,
                "reasoning": reasoning,
                "code_preview": generated_code[:300],
            },
        )

        if not generated_code.strip().startswith(f"def {fn_name}"):
            last_error = (
                f"Code does not start with 'def {fn_name}'. "
                f"Got: {generated_code[:120]}"
            )
            logger.warning(
                "llm_exec_with_retry | invalid function signature",
                extra={"fn_name": fn_name, "attempt": attempt + 1, "error": last_error},
            )
            continue

        local_env: Dict[str, Any] = {**exec_globals}
        try:
            exec(generated_code, local_env)  # noqa: S102
        except Exception as exc:
            last_error = f"exec() failed: {type(exc).__name__}: {exc}"
            logger.warning(
                "llm_exec_with_retry | exec failed",
                extra={"fn_name": fn_name, "attempt": attempt + 1, "error": last_error},
            )
            continue

        fn = local_env.get(fn_name)
        if not callable(fn):
            last_error = f"'{fn_name}' not found in exec scope."
            logger.warning(
                "llm_exec_with_retry | function not found after exec",
                extra={"fn_name": fn_name, "attempt": attempt + 1},
            )
            continue
        try:
            result = fn(**fn_kwargs)
            logger.info(
                "llm_exec_with_retry | success",
                extra={
                    "fn_name": fn_name,
                    "attempt": attempt + 1,
                    "result_type": type(result).__name__,
                },
            )
            return {"response": parsed, "result": result}
        except Exception as exc:
            last_error = f"{fn_name}() raised {type(exc).__name__}: {exc}"
            logger.warning(
                "llm_exec_with_retry | function call failed",
                extra={"fn_name": fn_name, "attempt": attempt + 1, "error": last_error},
            )
            continue

    logger.error(
        "llm_exec_with_retry | all attempts exhausted",
        extra={
            "fn_name": fn_name,
            "total_attempts": max_retries + 1,
            "last_error": last_error,
        },
    )
    raise RuntimeError(
        f"llm_exec_with_retry: all {max_retries + 1} attempts failed "
        f"for '{fn_name}'.\nLast error: {last_error}"
    )


def llm_service_claude(
    messages: List[BaseMessage], use_cache: bool = False
) -> dict | str:
    print("LLM Service called with messages:")
    for msg in messages:
        print(f"  {msg.type}: {msg.content}")
    llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)

    logger.debug(
        "llm_service | invoking LLM",
        extra={
            "message_count": len(messages),
            "last_message_role": (
                getattr(messages[-1], "type", "unknown") if messages else None
            ),
            "last_message_preview": (
                str(messages[-1].content)[:200] if messages else None
            ),
        },
    )

    if use_cache:
        cache_key = hashlib.md5(
            json.dumps(
                [{"role": m.type, "content": str(m.content)} for m in messages],
                sort_keys=True,
            ).encode()
        ).hexdigest()

        if cache_key in cache:
            logger.debug("llm_service | cache hit | key=%s", cache_key)
            return cache[cache_key]

    try:
        response = llm.invoke(messages)

        logger.debug(
            "llm_service | response received",
            extra={
                "response_preview": str(response.content)[:200],
                "response_type": type(response.content).__name__,
            },
        )
        try:
            cleaned_response_content = _extract_json(response.content)
            result = cleaned_response_content
        except Exception as e:
            logger.warning(
                "llm_service | json.loads failed, returning raw content",
                extra={"error": str(e)},
            )
            result = response.content

        if use_cache:
            cache[cache_key] = result
            logger.debug("llm_service | cache miss | stored key=%s", cache_key)

        return result

    except Exception as e:
        logger.error(
            "llm_service | LLM invocation failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise

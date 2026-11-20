with open('cloud/backend/stream_manager.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update worker signature
old_worker = 'def _stream_worker(state: StreamState, model_path: str, events_api_url: Optional[str],\n                   debounce_frames: int, conf_threshold: float) -> None:'
new_worker = 'def _stream_worker(state: StreamState, model_path: str, events_api_url: Optional[str],\n                   debounce_frames: int, conf_threshold: float, api_key: Optional[str] = None) -> None:'
text = text.replace(old_worker, new_worker)

# 2. Update post_event calls
text = text.replace(
    'if events_api_url:\n                    post_event(event, events_api_url)',
    'if events_api_url:\n                    post_event(event, events_api_url, api_key=api_key)'
)
text = text.replace(
    'if events_api_url:\n                                post_event(event, events_api_url)',
    'if events_api_url:\n                                post_event(event, events_api_url, api_key=api_key)'
)

# 3. Update start_stream signature
old_start = 'conf_threshold: float = 0.25,\n) -> Dict[str, Any]:'
new_start = 'conf_threshold: float = 0.25,\n    api_key: Optional[str] = None,\n) -> Dict[str, Any]:'
text = text.replace(old_start, new_start)

# 4. Update thread args
old_thread = 'args=(state, model_path, events_api_url, debounce_frames, conf_threshold),'
new_thread = 'args=(state, model_path, events_api_url, debounce_frames, conf_threshold, api_key),'
text = text.replace(old_thread, new_thread)

with open('cloud/backend/stream_manager.py', 'w', encoding='utf-8') as f:
    f.write(text)

print('Updated stream_manager.py')


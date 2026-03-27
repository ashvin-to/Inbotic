import os
from openai import OpenAI
from dotenv import load_dotenv
import logging
import time
import json
import re
import datetime

load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def _get_openrouter_client():
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        timeout=120.0,
    )
# Preferred model can be overridden via env; restrict to known free routes
MAIN_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
FALLBACK_MODELS = [
    MAIN_MODEL,
    "meta-llama/llama-3.1-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "openchat/openchat-7b:free",
    "gryphe/mythomax-l2-13b:free",
]
CURRENT_DATE = "2025-09-24"
MAX_RECURSION_DEPTH = 3

def estimate_tokens(text):
    return len(text) // 4 + text.count(' ') // 2

class LLMClient:
    @staticmethod
    def _chat_complete(messages, temperature=0.5, max_tokens=800):
        """Call OpenRouter with model fallbacks to avoid 404s for unavailable models."""
        last_err = None
        client = _get_openrouter_client()
        if client:
            for model in FALLBACK_MODELS:
                try:
                    res = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    return res.choices[0].message.content.strip()
                except Exception as e:
                    # If specific 404 for model not found, try next; otherwise remember and continue
                    last_err = e
                    continue
        else:
            last_err = RuntimeError("OPENROUTER_API_KEY is not set")
        
        # Fallback to Gemini if OpenRouter fails
        try:
            gemini_key = os.getenv("GEMINI_API_KEY")
            if gemini_key:
                from google import genai
                from google.genai import types
                
                client = genai.Client(api_key=gemini_key)
                
                # Construct prompt
                if len(messages) == 1 and messages[0]['role'] == 'user':
                    prompt_text = messages[0]['content']
                else:
                    prompt_text = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
                
                contents = [
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(text=prompt_text),
                        ],
                    ),
                ]
                
                generate_content_config = types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_tokens,
                )
                
                logger.info("Falling back to Gemini...")
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=generate_content_config,
                )
                return response.text
        except Exception as e:
            logger.error(f"Gemini fallback failed: {e}")

        raise RuntimeError(f"All model fallbacks failed: {last_err}")
    @staticmethod
    def compress(mail_text, depth=0):
        start_time = time.time()
        if estimate_tokens(mail_text) <= 1500:
            logger.info("Email short enough, no compression needed")
            return mail_text
        
        if depth >= MAX_RECURSION_DEPTH:
            logger.warning(f"Max recursion depth {MAX_RECURSION_DEPTH} reached, truncating to first 10000 chars")
            return mail_text[:10000]
        
        logger.info(f"Compressing email (depth {depth}): {len(mail_text)} chars (~{estimate_tokens(mail_text)} tokens)")
        chunks = []
        chunk_size_chars = 2000
        overlap_chars = 200
        start = 0
        while start < len(mail_text):
            end = start + chunk_size_chars
            if end < len(mail_text):
                next_para = mail_text.find('\n\n', end - 200, end + 200)
                if next_para != -1:
                    end = next_para
            chunk = mail_text[start:end]
            chunks.append(chunk)
            start = end - overlap_chars if end < len(mail_text) else len(mail_text)
        if start < len(mail_text):
            chunks.append(mail_text[start:])

        compressed_chunks = []
        for idx, chunk in enumerate(chunks):
            logger.info(f"Compressing chunk {idx+1}/{len(chunks)} (~{estimate_tokens(chunk)} tokens)")
            compress_prompt = f"""
            Compress this email chunk into a concise summary (under 800 words). Prioritize preserving all key context for hackathons/internships: event names, dates (e.g., MM/DD/YYYY, September 22, 2025), deadlines, locations, tasks, requirements, URLs, and quoted text. Ensure deadlines and tasks are explicitly retained. Ignore irrelevant parts like signatures, ads, or boilerplate.
            Chunk: {chunk}
            """
            try:
                compressed = LLMClient._chat_complete(
                    messages=[{"role": "user", "content": compress_prompt}],
                    temperature=0.5,
                    max_tokens=1000,
                )
                if compressed:
                    compressed_chunks.append(compressed)
                else:
                    logger.warning(f"Empty compression for chunk {idx+1}, using original chunk")
                    compressed_chunks.append(chunk)
            except Exception as e:
                logger.error(f"Compression error for chunk {idx+1}: {e}")
                compressed_chunks.append(chunk)

        combined = "\n\n".join(compressed_chunks)
        if time.time() - start_time > 120:
            logger.warning("Compression timeout, using truncated version")
            return combined[:8000]
        if estimate_tokens(combined) > 2000:
            logger.info(f"Recursively compressing combined result (~{estimate_tokens(combined)} tokens)")
            return LLMClient.compress(combined, depth + 1)
        logger.info(f"Compression complete: {len(combined)} chars (~{estimate_tokens(combined)} tokens)")
        return combined

    @staticmethod
    def analyze(mail_text):
        compressed_text = LLMClient.compress(mail_text)
        logger.info(f"Processing compressed text: {len(compressed_text)} chars (~{estimate_tokens(compressed_text)} tokens)")
        
        summaries = []
        tasks_list = []
        max_tokens_per_chunk = 2000
        overlap_chars = 200

        if estimate_tokens(compressed_text) > max_tokens_per_chunk:
            logger.info(f"Chunking compressed email: ~{estimate_tokens(compressed_text)} tokens")
            chunks = []
            start = 0
            while start < len(compressed_text):
                end = start + max_tokens_per_chunk * 4
                if end < len(compressed_text):
                    next_para = compressed_text.find('\n\n', end - 200, end + 200)
                    if next_para != -1:
                        end = next_para
                chunk = compressed_text[start:end]
                chunks.append(chunk)
                start = end - overlap_chars if end < len(compressed_text) else len(compressed_text)
            if start < len(compressed_text):
                chunks.append(compressed_text[start:])
        else:
            chunks = [compressed_text]

        default_due_date = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        for idx, chunk in enumerate(chunks):
            logger.info(f"Analyzing chunk {idx+1}/{len(chunks)} (~{estimate_tokens(chunk)} tokens)")
            prompt = f"""
            Analyze this compressed email chunk related to hackathons or internships. Today's date is {CURRENT_DATE}. Provide:
            - A summary in 3 bullet points, focusing on key details (e.g., event name, dates in MM/DD/YYYY, location, URLs).
            - A list of actionable tasks or deadlines for opportunities. Output tasks as valid JSON: ```json\n[{{"task": "description", "due_date": "YYYY-MM-DD"}}]\n```.
            - Include tasks for opportunities even if no explicit deadline is mentioned (use {default_due_date} as default).
            - If a URL is provided for applying or getting details, include it in the task description (e.g., "Apply via [URL]").
            - Ignore deadlines before {CURRENT_DATE}.
            - Ensure JSON is complete and valid.
            Chunk: {chunk}
            """
            try:
                text = LLMClient._chat_complete(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=600,
                )
                json_match = re.search(r'```json\n(.*?)\n```', text, re.DOTALL)
                chunk_tasks = []
                if json_match:
                    try:
                        chunk_tasks = json.loads(json_match.group(1))
                        for task in chunk_tasks:
                            url_match = re.search(r'https?://[^\s]+', task.get('task', ''))
                            if url_match and not task.get('due_date'):
                                url = url_match.group(0)
                                deadline = LLMClient.fetch_url_deadline(url)
                                if deadline:
                                    task['due_date'] = deadline
                                elif not task.get('due_date'):
                                    task['due_date'] = default_due_date
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON in chunk {idx+1}: {e}")
                chunk_summary = text[:json_match.start()].strip() if json_match else text.strip()
                summaries.append(f"Chunk {idx+1}:\n{chunk_summary}")
                if chunk_tasks:
                    tasks_list.extend(chunk_tasks)
            except Exception as e:
                logger.error(f"Error analyzing chunk {idx+1}: {e}")
                return None, f"Failed to analyze email: {e}"

        combined_summary = "\n\n".join(summaries) if summaries else "No summary generated."
        combined_tasks = json.dumps(tasks_list) if tasks_list else "[]"
        logger.info(f"Analysis complete: Summary: {combined_summary[:50]}..., Tasks: {combined_tasks[:50]}...")
        return combined_summary, combined_tasks
    

    @staticmethod
    def fetch_url_deadline(url):
        try:
            import requests
            from bs4 import BeautifulSoup
            response = requests.get(url, timeout=5)
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text()
            date_pattern = r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b'
            dates = re.findall(date_pattern, text)
            for date_str in dates:
                try:
                    parsed_date = datetime.datetime.strptime(date_str, '%B %d, %Y')
                    if parsed_date.date() > datetime.datetime.strptime(CURRENT_DATE, '%Y-%m-%d').date():
                        return parsed_date.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            return None
        except Exception as e:
            logger.error(f"Failed to fetch deadline from {url}: {e}")
            return None

    @staticmethod
    def review_tasks(tasks: list[dict]) -> str:
        """Review a set of existing tasks and produce a concise plan.

        Input format per task dict: {"title": str, "due": "YYYY-MM-DD"|None, "list": str|None, "status": str|None}
        Returns markdown text with:
          - prioritized list (near-term first)
          - per-task suggestions (missing info, potential next action)
          - a short schedule for the next 7 days
        """
        try:
            # Build a compact JSON-like description for the prompt
            import json, datetime as _dt
            today = _dt.date.today().isoformat()
            summary_items = []
            for t in tasks:
                summary_items.append({
                    "title": t.get("title", ""),
                    "due": t.get("due"),
                    "list": t.get("list"),
                    "status": t.get("status"),
                    "link": t.get("link"),  # Include link if available
                })
            prompt = (
                "You are a productivity assistant. Today is " + today +
                ". Given these tasks (JSON), produce a clean, readable markdown report.\n"
                "1) **Prioritized List**: List tasks in order of urgency (near-term first). Use bullet points. "
                "For each task, include the due date (if any) and one concise actionable next step. "
                "If a task has a 'link', include it as a markdown link [Open Email](url) at the end of the line.\n"
                "2) **7-Day Schedule**: Group tasks by day for the next 7 days. If a day has no tasks, omit it.\n"
                "Do NOT output raw JSON blocks. Use clean Markdown formatting (headers, lists, bold text).\n\nTasks JSON:\n" + json.dumps(summary_items, ensure_ascii=False, indent=2)
            )

            text = LLMClient._chat_complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=1500,  # Increased for longer task lists
            )
            return text
        except Exception as e:
            logger.error(f"review_tasks failed: {e}")
            return "Could not generate review at this time."

    @staticmethod
    def chat_with_data(query: str, context_data: str) -> str:
        """Chat with the LLM using provided context data (RAG)."""
        try:
            prompt = (
                f"You are a helpful assistant for Inbotic. "
                f"Use the following context (emails and tasks) to answer the user's question.\n\n"
                f"Context:\n{context_data}\n\n"
                f"User Question: {query}\n\n"
                f"Answer:"
            )
            
            return LLMClient._chat_complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=500,
            )
        except Exception as e:
            logger.error(f"chat_with_data failed: {e}")
            return "I'm sorry, I encountered an error processing your request."

    @staticmethod
    def extract_task_from_email(email_body: str, subject: str) -> dict:
        """Extract task details from email body using LLM when regex fails."""
        try:
            import datetime as _dt
            today = _dt.date.today().isoformat()
            
            prompt = (
                f"Analyze this email and extract a task if one exists. Today is {today}.\n"
                f"Subject: {subject}\n"
                f"Body: {email_body[:2000]}\n\n"
                f"Return a JSON object with keys: 'title', 'due_date' (YYYY-MM-DD), 'description'.\n"
                f"If no explicit deadline, try to infer one or use null.\n"
                f"If no task found, return null.\n"
                f"Output ONLY valid JSON, no explanations."
            )
            
            text = LLMClient._chat_complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,  # Increased to prevent truncation
            )
            
            # Log the raw response for debugging
            logger.info(f"LLM response for task extraction: {text[:200]}...")
            
            # Clean up potential markdown code blocks
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            # Try to find JSON object in response
            text = text.strip()
            if text.lower() == "null" or text.lower() == "none":
                return None
            
            # Find JSON object boundaries
            start_idx = text.find("{")
            end_idx = text.rfind("}") + 1
            if start_idx != -1 and end_idx > start_idx:
                text = text[start_idx:end_idx]
                
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error in extract_task_from_email: {e}")
            logger.error(f"Raw text was: {text[:200] if 'text' in dir() else 'N/A'}")
            return None
        except Exception as e:
            logger.error(f"extract_task_from_email failed: {e}")
            return None

if __name__ == "__main__":
    email = "Subject: Qualcomm Internship\nApply for the Qualcomm IT Interim Intern role at https://unstop.com/internship. Stipend: ₹30,000."
    compressed = LLMClient.compress(email)
    print("Compressed:", len(compressed))
    summary, tasks = LLMClient.analyze(email)
    print("Tasks:", tasks)
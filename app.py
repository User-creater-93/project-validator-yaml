import streamlit as st
import yaml
from typing import Dict, List, Any, Optional, Set, Tuple

st.set_page_config(page_title="YAMLScript Validator", page_icon="🤖")

# --- ЛОГИКА СБРОСА ---
if 'form_id' not in st.session_state:
    st.session_state.form_id = 0

def clear_form():
    st.session_state.form_id += 1

# Функция валидации (без изменений)
def run_validation(rules_content: str) -> Tuple[Dict[str, List], bool]:
    try:
        rules_data = yaml.safe_load(rules_content) or {}
        rules = rules_data.get('rules', []) if isinstance(rules_data, dict) else rules_data
        if not isinstance(rules, list): rules = [rules]

        action_slots_map = {}
        slot_consistency_errors = []
        coverage_map = {} 

        def prettify_val(val: Any) -> str:
            v = str(val).lower()
            if v == 'true': return 'true'
            if v == 'false': return 'false'
            if v in ['none', 'null', '', 'none-type']: return 'null'
            return str(val)

        for rule in rules:
            if not isinstance(rule, dict): continue
            steps_raw = rule.get('steps', [])
            if not isinstance(steps_raw, list): continue
            steps = []
            for s in steps_raw:
                if isinstance(s, list): steps.extend(s)
                else: steps.append(s)
            
            history = [] 
            for i, step in enumerate(steps):
                if not isinstance(step, dict): continue
                if 'intent' in step:
                    raw_intent = step['intent']
                    intent_name = "yes" if raw_intent is True else "no" if raw_intent is False else str(raw_intent)
                    history.append(f"intent: {intent_name}")
                elif 'or' in step and isinstance(step['or'], list):
                    intents_in_or = []
                    for or_item in step['or']:
                        if isinstance(or_item, dict) and 'intent' in or_item:
                            raw_i = or_item['intent']
                            name = "yes" if raw_i is True else "no" if raw_i is False else str(raw_i)
                            intents_in_or.append(name)
                    if intents_in_or:
                        history.append(f"intent (or): {'/'.join(intents_in_or)}")
                if 'action' in step:
                    act_name = str(step['action'])
                    history.append(f"action: {act_name}")
                    is_cleaning_action = "get-cleaning" in act_name
                    current_slot_names = []
                    if i + 1 < len(steps):
                        next_step = steps[i+1]
                        if isinstance(next_step, dict) and 'slot_was_set' in next_step:
                            slots_raw = next_step['slot_was_set']
                            slots_list = slots_raw if isinstance(slots_raw, list) else [slots_raw]
                            for s_item in slots_list:
                                if isinstance(s_item, dict):
                                    for s_name, s_val in s_item.items():
                                        current_slot_names.append(s_name)
                                        if not is_cleaning_action:
                                            val_to_store = str(s_val).lower()
                                            ctx = tuple(history[:])
                                            cov_key = (ctx, s_name)
                                            if cov_key not in coverage_map: coverage_map[cov_key] = set()
                                            coverage_map[cov_key].add(val_to_store)
                    current_sequence = [str(x) for x in current_slot_names]
                    if act_name in action_slots_map:
                        if current_sequence != action_slots_map[act_name]:
                            slot_consistency_errors.append({"action": act_name, "rule": rule.get('rule', 'Без названия'), "expected": action_slots_map[act_name], "found": current_sequence})
                    else: action_slots_map[act_name] = current_sequence
                if 'slot_was_set' in step:
                    slots_raw = step['slot_was_set']
                    slots_list = slots_raw if isinstance(slots_raw, list) else [slots_raw]
                    for s_item in slots_list:
                        if isinstance(s_item, dict):
                            for sn, sv in s_item.items(): history.append(f"{sn}: {prettify_val(sv)}")

        coverage_errors = []
        null_vals = {'null', 'none', '', 'none-type'}
        for (ctx, s_name), found_values in coverage_map.items():
            missing = []
            has_true, has_false = "true" in found_values, "false" in found_values
            has_explicit_set = any(v.lower() == "set" for v in found_values)
            has_null = any(v in null_vals for v in found_values)
            has_other_val = any(v not in null_vals and v not in ['true', 'false', 'set'] for v in found_values)
            if has_true and not has_false: missing.append("False")
            elif has_false and not has_true: missing.append("True")
            if has_explicit_set and not has_null: missing.append("null")
            if has_null and not has_explicit_set and not (has_true or has_false or has_other_val): missing.append("Set")
            if missing: coverage_errors.append({"slot": s_name, "missing": missing, "context": "\n".join(ctx)})

        return {"🔴 Конфликты слотов после Action": slot_consistency_errors, "🟡 Не найдены rule со значениями (Coverage)": coverage_errors}, False
    except Exception as e:
        return {"Ошибка синтаксиса YAML": [str(e)]}, False

def get_data(uploaded, text_input):
    if text_input and text_input.strip(): return text_input
    if uploaded: return uploaded.getvalue().decode("utf-8")
    return None

# --- ИНТЕРФЕЙС ---
st.title("🤖 YAMLScript Validator")

input_method = st.radio("Выберите способ ввода:", ["Текст", "Загрузка файла"], horizontal=True)

with st.form("main_logic_form"):
    raw_yaml_input = ""
    rules_file = None

    if input_method == "Текст":
        # Ключ для мгновенной очистки
        raw_yaml_input = st.text_area("Вставьте YAML сценарий сюда:", height=300, placeholder="rules: ...", key=f"txt_{st.session_state.form_id}")
    else:
        # Ключ для мгновенной очистки
        rules_file = st.file_uploader("Загрузить правила (.yml)", type=['yml', 'yaml'], key=f"file_{st.session_state.form_id}")

    run_btn = st.form_submit_button("🚀 Запустить валидацию", use_container_width=True)

if run_btn:
    r_data = get_data(rules_file, raw_yaml_input)
    if not r_data:
        st.error("⚠️ Данные не найдены. Вставьте текст или выберите файл.")
    else:
        with st.spinner("Анализирую..."):
            results, _ = run_validation(r_data)
            st.divider()
        
        if not any(results.values()):
            st.success("✅ Ошибок не найдено.")
            if st.button("🧹 Очистить форму", use_container_width=True):
                clear_form()
                st.rerun()
        else:
            if st.button("🧹 Очистить форму", use_container_width=True):
                clear_form()
                st.rerun()

            for title, issues in results.items():
                if not issues: continue
                if title == "Ошибка синтаксиса YAML":
                    for err in issues: st.error(f"⚠️ {title}: {err}")
                else:
                    with st.expander(f"{title} ({len(issues)})", expanded=False):
                        if "Конфликты" in title:
                            for err in issues:
                                st.markdown(f"**Action:** `{err['action']}`  \nRule: {err['rule']}")
                                c1, c2 = st.columns(2)
                                c1.info(f"**Ожидается:**\n\n " + "  \n".join(err['expected']) if err['expected'] else "Нет слотов")
                                c2.warning(f"**Найдено:**\n\n " + "  \n".join(err['found']) if err['found'] else "Нет слотов")
                                st.divider()
                        elif "Coverage" in title:
                            for err in issues:
                                st.error(f"Слот `{err['slot']}`: отсутствует {err['missing']}")
                                st.code(err['context'], language="text")
                                st.divider()
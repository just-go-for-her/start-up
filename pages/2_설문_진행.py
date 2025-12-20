import streamlit as st
import json
import pandas as pd
from datetime import datetime
import os
import uuid
import numpy as np

# ==============================================================================
# [설정] URL
# ==============================================================================
FULL_URL = "https://ahp-platform-bbee45epwqjjy2zfpccz7p.streamlit.app/%EC%84%A4%EB%AC%B8_%EC%A7%84%ED%96%89"
CONFIG_DIR = "survey_config"
os.makedirs(CONFIG_DIR, exist_ok=True)

st.set_page_config(page_title="설문 진행", page_icon="📝", layout="wide")

# ==============================================================================
# [CSS 스타일링] - 붉은 테두리 및 카드 디자인
# ==============================================================================
st.markdown("""
<style>
    .rank-card {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #dee2e6;
        text-align: center;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        margin-bottom: 10px;
    }
    .rank-card-red {
        background-color: #fff5f5;
        padding: 15px;
        border-radius: 10px;
        border: 3px solid #fa5252; /* 붉은 테두리 */
        text-align: center;
        box-shadow: 0 0 10px rgba(250, 82, 82, 0.4);
        margin-bottom: 10px;
    }
    .rank-title { font-weight: bold; font-size: 1.1em; margin-bottom: 5px; }
    .rank-info { font-size: 0.9em; color: #666; }
    .rank-current { font-weight: bold; color: #228be6; font-size: 1.0em; }
    .rank-current-red { font-weight: bold; color: #fa5252; font-size: 1.0em; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# [함수] AHP 계산 로직 (파이썬)
# ==============================================================================
def calculate_current_ranks(items, matrix):
    """현재 매트릭스 기반 가중치 및 순위 계산"""
    n = len(items)
    # 기하평균법 사용 (실시간 계산에 빠름)
    weights = []
    for i in range(n):
        row_prod = np.prod(matrix[i])
        weights.append(row_prod ** (1/n))
    
    total_weight = sum(weights)
    norm_weights = [w / total_weight for w in weights]
    
    # 가중치 내림차순으로 순위 매기기 (동점 처리 포함)
    indexed_weights = sorted(enumerate(norm_weights), key=lambda x: x[1], reverse=True)
    
    rank_map = {}
    current_rank = 1
    for i in range(len(indexed_weights)):
        idx, w = indexed_weights[i]
        if i > 0 and abs(w - indexed_weights[i-1][1]) < 0.00001:
            pass # 동점이면 랭크 유지
        else:
            current_rank = i + 1
        rank_map[idx] = current_rank
        
    return rank_map, norm_weights

# ==============================================================================
# [메인 로직]
# ==============================================================================

# 1. URL 파라미터 및 설정 로드
query_params = st.query_params
raw_id = query_params.get("id", None)
survey_id = raw_id if raw_id else None

survey_data = None
if survey_id:
    config_path = os.path.join(CONFIG_DIR, f"{survey_id}.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            survey_data = json.load(f)
    else:
        st.error("유효하지 않은 링크입니다.")
        st.stop()
else:
    survey_data = st.session_state.get("passed_structure", None)

if not survey_data:
    st.warning("설문 데이터를 불러올 수 없습니다.")
    st.stop()

st.title(f"📝 {survey_data['goal']}")

# 2. 데이터 준비 (Flatten Tasks)
if 'tasks' not in st.session_state:
    tasks = []
    if len(survey_data["main_criteria"]) > 1:
        tasks.append({"name": "평가 기준 중요도", "items": survey_data["main_criteria"]})
    for cat, items in survey_data["sub_criteria"].items():
        if len(items) > 1:
            tasks.append({"name": f"[{cat}] 세부 항목", "items": items})
    st.session_state['tasks'] = tasks
    st.session_state['current_task_idx'] = 0
    st.session_state['step'] = 'ranking' # ranking -> compare -> finish
    st.session_state['answers'] = {}

# 현재 작업 정보
tasks = st.session_state['tasks']
if st.session_state['current_task_idx'] >= len(tasks):
    st.session_state['step'] = 'finish'

# ==============================================================================
# [UI] 단계별 화면
# ==============================================================================

if st.session_state['step'] == 'finish':
    st.success("모든 설문이 완료되었습니다!")
    st.text_area("결과 코드", json.dumps(st.session_state['answers'], ensure_ascii=False, indent=2), height=200)
    
    with st.form("final_submit"):
        name = st.text_input("응답자 성함")
        if st.form_submit_button("최종 제출"):
            # 저장 로직
            goal_clean = survey_data["goal"].replace(" ", "_")
            secret_key = survey_data.get("secret_key", "public")
            file_path = f"survey_data/{secret_key}_{goal_clean}.csv"
            save_dict = {"Time": datetime.now().strftime("%Y-%m-%d %H:%M"), "Respondent": name, "Raw_Data": json.dumps(st.session_state['answers'])}
            df = pd.DataFrame([save_dict])
            try: old_df = pd.read_csv(file_path)
            except: old_df = pd.DataFrame()
            pd.concat([old_df, df], ignore_index=True).to_csv(file_path, index=False)
            st.success("제출되었습니다!")
            st.stop()

elif st.session_state['step'] == 'ranking':
    # --------------------------------------------------------------------------
    # 1단계: 순위 설정
    # --------------------------------------------------------------------------
    current_task = tasks[st.session_state['current_task_idx']]
    items = current_task['items']
    
    st.subheader(f"Step 1. {current_task['name']} - 순위 설정")
    st.info("각 항목의 중요도 순위를 설정해주세요.")

    # 순위 입력 폼
    initial_ranks = {}
    cols = st.columns(len(items))
    for idx, item in enumerate(items):
        with cols[idx]:
            rank = st.selectbox(f"{item} 순위", options=range(1, len(items)+1), key=f"rank_{idx}")
            initial_ranks[idx] = rank
    
    if st.button("설문 시작하기", type="primary"):
        # 중복 체크
        if len(set(initial_ranks.values())) != len(items):
            st.error("순위가 중복되었습니다. 서로 다른 순위를 지정해주세요.")
        else:
            # 초기화 및 다음 단계로 이동
            st.session_state['initial_ranks'] = initial_ranks
            st.session_state['matrix'] = np.ones((len(items), len(items)))
            
            # 비교 쌍 생성
            pairs = []
            sorted_indices = sorted(initial_ranks, key=initial_ranks.get) # 순위대로 정렬
            for i in range(len(sorted_indices)):
                for j in range(i + 1, len(sorted_indices)):
                    u, v = sorted_indices[i], sorted_indices[j]
                    pairs.append({'u': u, 'v': v, 'a': items[u], 'b': items[v]})
            
            st.session_state['pairs'] = pairs
            st.session_state['pair_idx'] = 0
            st.session_state['step'] = 'compare'
            st.rerun()

elif st.session_state['step'] == 'compare':
    # --------------------------------------------------------------------------
    # 2단계: 쌍대 비교 (여기가 핵심)
    # --------------------------------------------------------------------------
    current_task = tasks[st.session_state['current_task_idx']]
    items = current_task['items']
    pairs = st.session_state['pairs']
    pair_idx = st.session_state['pair_idx']
    
    # 완료 시 다음 태스크로
    if pair_idx >= len(pairs):
        st.session_state['current_task_idx'] += 1
        st.session_state['step'] = 'ranking'
        st.rerun()

    p = pairs[pair_idx]
    
    # --- [상단] 랭킹 보드 (Red Border 로직 적용) ---
    rank_map, weights = calculate_current_ranks(items, st.session_state['matrix'])
    initial_ranks = st.session_state['initial_ranks']
    
    # 역전 감지 (쌍방 체크)
    flipped_indices = set()
    for i in range(len(items)):
        for j in range(len(items)):
            if i == j: continue
            # 조건: 원래 i가 더 높았는데(숫자 작음), 현재 랭크가 더 낮아짐(숫자 큼)
            if initial_ranks[i] < initial_ranks[j] and rank_map[i] > rank_map[j]:
                flipped_indices.add(i)
                flipped_indices.add(j)

    st.subheader(f"📊 실시간 순위 현황")
    
    # 카드 렌더링
    board_cols = st.columns(len(items))
    sorted_display = sorted(range(len(items)), key=lambda x: initial_ranks[x])
    
    for idx, item_idx in enumerate(sorted_display):
        is_flipped = item_idx in flipped_indices
        css_class = "rank-card-red" if is_flipped else "rank-card"
        text_class = "rank-current-red" if is_flipped else "rank-current"
        
        with board_cols[idx]:
            st.markdown(f"""
            <div class="{css_class}">
                <div class="rank-title">{items[item_idx]}</div>
                <div class="rank-info">설정: {initial_ranks[item_idx]}위</div>
                <div class="{text_class}">현재: {rank_map[item_idx]}위</div>
            </div>
            """, unsafe_allow_html=True)

    if flipped_indices:
        st.warning("⚠️ 순위 역전이 감지되었습니다! (붉은 테두리 항목)")

    # --- [중단] 질문 카드 ---
    st.markdown("---")
    st.markdown(f"### Q{pair_idx+1}. 두 항목 중 무엇이 더 중요합니까?")
    
    col1, col2, col3 = st.columns([1, 8, 1])
    with col1: st.markdown(f"<h3 style='text-align:right; color:#228be6'>{p['a']}</h3>", unsafe_allow_html=True)
    with col3: st.markdown(f"<h3 style='text-align:left; color:#fa5252'>{p['b']}</h3>", unsafe_allow_html=True)
    
    with col2:
        # 슬라이더 값 매핑 로직
        # 0: 동등, -1~-4: A우세, 1~4: B우세
        
        # 이전 값이 있으면 불러오기
        prev_val = 0
        current_val = st.slider("비교", min_value=-4, max_value=4, value=0, step=1, key=f"slider_{pair_idx}", label_visibility="collapsed")
        
        # 텍스트 표시
        if current_val == 0:
            st.markdown("<h4 style='text-align:center;'>동등함 (1:1)</h4>", unsafe_allow_html=True)
        elif current_val < 0:
            st.markdown(f"<h4 style='text-align:center; color:#228be6'>{p['a']} 가 {abs(current_val)+1}배 중요</h4>", unsafe_allow_html=True)
        else:
            st.markdown(f"<h4 style='text-align:center; color:#fa5252'>{p['b']} 가 {abs(current_val)+1}배 중요</h4>", unsafe_allow_html=True)

    # --- [하단] 네비게이션 버튼 (핵심 요청 사항) ---
    st.markdown("<br>", unsafe_allow_html=True)
    b_col1, b_col2 = st.columns([1, 1])
    
    # 버튼 로직
    with b_col1:
        if pair_idx == 0:
            # 첫 질문일 때 -> 순위 재설정 버튼 (붉은색 스타일)
            if st.button("🔄 순위 재설정", type="primary", use_container_width=True):
                st.session_state['step'] = 'ranking'
                st.rerun()
        else:
            # 이후 질문 -> 이전 버튼
            if st.button("⬅ 이전 질문", use_container_width=True):
                st.session_state['pair_idx'] -= 1
                st.rerun()
    
    with b_col2:
        if st.button("다음 질문 ➡", type="secondary", use_container_width=True):
            # 값 저장 로직 (파이썬)
            val = current_val
            w = 1.0
            if val == 0: w = 1.0
            elif val < 0: w = abs(val) + 1.0 # A 우세
            else: w = 1.0 / (val + 1.0)      # B 우세
            
            # 매트릭스 업데이트
            st.session_state['matrix'][p['u']][p['v']] = w
            st.session_state['matrix'][p['v']][p['u']] = 1.0 / w
            
            # 결과 기록
            k = f"[{current_task['name']}] {p['a']} vs {p['b']}"
            st.session_state['answers'][k] = round(w, 3)
            
            # 인덱스 증가
            st.session_state['pair_idx'] += 1
            st.rerun()

import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import re

# ==========================================
# 1. 스트림릿 페이지 기본 설정
# ==========================================
st.set_page_config(
    page_title="우리동네 학령인구 분석기",
    page_icon="🎒",
    layout="wide"
)

# ==========================================
# 2. 데이터 로딩 및 전처리 (학령인구 특화)
# ==========================================

@st.cache_data(show_spinner="전국 연령별 인구 데이터를 분석 중입니다...")
def load_education_data():
    csv_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    
    # 1. 데이터 로드
    df = pd.read_csv(csv_url, compression='gzip', dtype={'코드': str})
    
    # 코드 전처리 및 최신 연도 필터링
    df['코드'] = df['코드'].str.zfill(10)
    df['sigungu_code'] = df['코드'].str[:5]
    latest_year = df['연도'].max()
    df_latest = df[df['연도'] == latest_year].copy()
    
    # 2. 학령인구(0세~18세) 열 추출
    age_cols_map = {}
    total_cols = []
    
    for col in df_latest.columns:
        if col.startswith('계_'):
            total_cols.append(col)
            match = re.search(r'계_(\d+)세', col)
            if match:
                age = int(match.group(1))
                if 0 <= age <= 18:  # 0세부터 18세까지만 추출
                    age_cols_map[col] = age

    # 3. 데이터 재구조화 (Melt)
    df_kids = df_latest[['sigungu_code', '시도', '시군구', '동'] + list(age_cols_map.keys())]
    df_melt = df_kids.melt(id_vars=['sigungu_code', '시도', '시군구', '동'], var_name='연령_원본', value_name='인구')
    df_melt['연령'] = df_melt['연령_원본'].map(age_cols_map)
    
    # 학령기 구분 (영유아 / 초등 / 중고등)
    bins = [-1, 6, 12, 18]
    labels = ['영유아(0-6)', '초등(7-12)', '중고등(13-18)']
    df_melt['학령기'] = pd.cut(df_melt['연령'], bins=bins, labels=labels)
    
    # 4. 시군구 단위 집계 (지도용)
    df_sigungu = df_melt.groupby(['sigungu_code', '시도', '시군구', '학령기'])['인구'].sum().reset_index()
    
    # 시군구별 총인구 합산 (비율 계산용)
    df_latest['시군구_총인구'] = df_latest[total_cols].sum(axis=1)
    df_total_sum = df_latest.groupby('sigungu_code')['시군구_총인구'].sum().reset_index()
    
    df_sigungu = pd.merge(df_sigungu, df_total_sum, on='sigungu_code')
    df_sigungu['비율'] = (df_sigungu['인구'] / df_sigungu['시군구_총인구']) * 100
    
    return df_melt, df_sigungu, latest_year

@st.cache_data
def load_geojson():
    geojson_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    return requests.get(geojson_url).json()

# 데이터 로드 실행
df_detail, df_map, data_year = load_education_data()
geojson_data = load_geojson()


# ==========================================
# 3. 사이드바 검색 및 필터 (기본값: 제주특별자치도 제주시)
# ==========================================
st.sidebar.title("🎒 지역 교육 인구 필터")
st.sidebar.markdown(f"**기준 연도: {data_year}년**")

# 1) 시/도 선택 ('제주특별자치도'를 기본 선택)
sido_list = sorted(df_detail['시도'].unique())
default_sido_index = sido_list.index('제주특별자치도') if '제주특별자치도' in sido_list else 0
selected_sido = st.sidebar.selectbox("1️⃣ 시/도 선택", sido_list, index=default_sido_index)

# 2) 시/군/구 선택 ('제주시'를 기본 선택)
sigungu_list = sorted(df_detail[df_detail['시도'] == selected_sido]['시군구'].unique())
default_sigungu_index = sigungu_list.index('제주시') if '제주시' in sigungu_list else 0
selected_sigungu = st.sidebar.selectbox("2️⃣ 시/군/구 상세 선택", sigungu_list, index=default_sigungu_index)

st.sidebar.markdown("---")
st.sidebar.info("💡 **팁**: 지도의 학령기 탭을 변경하여 지역별 교육 수요를 예측해 보세요.")


# ==========================================
# 4. 메인 화면 - 선택 지역 세부 연령 분포
# ==========================================
st.title("🎒 우리동네 학령인구 분석 대시보드")
st.subheader(f"{selected_sido} {selected_sigungu}의 0세~18세 상세 연령 분포")

# 선택된 지역 데이터 필터링 및 연령별 합산
df_target = df_detail[
    (df_detail['시도'] == selected_sido) & 
    (df_detail['시군구'] == selected_sigungu)
].groupby('연령')['인구'].sum().reset_index()

# 학령기 색상 매핑
school_colors = {'영유아(0-6)': '#8dd3c7', '초등(7-12)': '#ffffb3', '중고등(13-18)': '#bebada'}
bins = [-1, 6, 12, 18]
labels = ['영유아(0-6)', '초등(7-12)', '중고등(13-18)']
df_target['학령기'] = pd.cut(df_target['연령'], bins=bins, labels=labels)

# 세부 연령 바 차트 생성
fig_bar = px.bar(
    df_target,
    x='연령',
    y='인구',
    color='학령기',
    color_discrete_map=school_colors,
    text_auto=',d',  # 천단위 콤마 표기
    title=f"{selected_sigungu} 연령별 인구 현황"
)

fig_bar.update_layout(
    xaxis=dict(tickmode='linear', dtick=1, title="연령 (세)"),
    yaxis=dict(title="인구 (명)"),
    showlegend=True,
    height=350,
    margin=dict(l=10, r=10, t=40, b=10)
)
st.plotly_chart(fig_bar, use_container_width=True)

st.markdown("---")


# ==========================================
# 5. 메인 화면 - 하단 전국 지도 비교
# ==========================================
st.subheader("🗺️ 전국 시군구별 학령기 인구 비율 (%)")

# 탭을 통해 학령기별 지도 전환
tabs = st.tabs(labels)

for i, tab in enumerate(tabs):
    with tab:
        current_stage = labels[i]
        df_map_stage = df_map[df_map['학령기'] == current_stage]
        
        # 학령기별 지도 테마 색상 지정
        if i == 0: scale = "Mint"
        elif i == 1: scale = "YlOrRd"
        else: scale = "Purples"
        
        # 단계구분도 생성
        fig_map = px.choropleth(
            df_map_stage,
            geojson=geojson_data,
            locations='sigungu_code',
            featureidkey="properties.코드",
            color='비율',
            color_continuous_scale=scale,
            hover_name='시군구',
            hover_data={'시도': True, '비율': ':.2f%', '인구': ':,', 'sigungu_code': False},
            labels={'비율': '비율(%)', '인구': '인구(명)'}
        )
        
        # 지도 스타일 및 크기 설정
        fig_map.update_geos(fitbounds="locations", visible=False)
        fig_map.update_layout(
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            height=550,
            coloraxis_colorbar=dict(title=f"{current_stage}<br>비율(%)")
        )
        
        st.plotly_chart(fig_map, use_container_width=True, key=f"map_{i}")

st.caption(f"자료 출처: 통계청 연령별 인구 현황 ({data_year}년 기준)")

import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
import re

# ==========================================
# 1. 스트림릿 페이지 기본 설정
# ==========================================
st.set_page_config(
    page_title="전국 지방소멸 위험지수 타임랩스 대시보드",
    page_icon="🚨",
    layout="wide"
)

# ==========================================
# 2. 데이터 로딩 및 전처리 함수
# ==========================================

# GeoJSON 시군구 경계 데이터 로드
@st.cache_data
def load_geojson():
    geojson_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    response = requests.get(geojson_url)
    return response.json()

# 전 연도 인구 데이터 로드 및 소멸위험지수 계산
@st.cache_data
def load_extinction_data():
    csv_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    
    # 행정동 코드를 10자리 문자열로 유보하여 읽기
    df = pd.read_csv(csv_url, compression='gzip', dtype={'코드': str})
    df['코드'] = df['코드'].astype(str).str.zfill(10)
    df['sigungu_code'] = df['코드'].str[:5]
    
    # 1. 열 분류 (전체 인구, 20~39세 여성, 65세 이상 전체)
    total_cols = [col for col in df.columns if col.startswith('계_')]
    
    # 여성 인구 열 중 20세~39세 열 필터링
    female_cols = [col for col in df.columns if col.startswith('여_')]
    female_20_39_cols = []
    for col in female_cols:
        match = re.search(r'\d+', col)
        if match and 20 <= int(match.group()) <= 39:
            female_20_39_cols.append(col)
            
    # 고령 인구 열 중 65세 이상 열 필터링
    age65_cols = []
    for col in total_cols:
        match = re.search(r'\d+', col)
        if match and int(match.group()) >= 65:
            age65_cols.append(col)
            
    # 2. 읍면동 단위에서 필요한 인구 수 합산
    df['총인구'] = df[total_cols].sum(axis=1)
    df['여성_20_39'] = df[female_20_39_cols].sum(axis=1)
    df['고령인구_65'] = df[age65_cols].sum(axis=1)
    
    # 3. (연도, 시군구) 단위로 그룹화하여 합산
    grouped = df.groupby(['연도', 'sigungu_code']).agg(
        시도=('시도', 'first'),
        시군구=('시군구', 'first'),
        총인구=('총인구', 'sum'),
        여성_20_39=('여성_20_39', 'sum'),
        고령인구_65=('고령인구_65', 'sum')
    ).reset_index()
    
    # 4. 지방소멸위험지수 계산 = (20~39세 여성 인구) / (65세 이상 고령 인구)
    # 0으로 나누는 오류 방지 (고령인구가 0인 경우 0.0001로 대치)
    grouped['소멸위험지수'] = grouped['여성_20_39'] / grouped['고령인구_65'].replace(0, 0.0001)
    grouped['소멸위험지수'] = grouped['소멸위험지수'].round(3)
    
    # 5. 소멸위험지수 5단계 위험 등급 분류 (마스다 히로야 기준)
    bins = [-float('inf'), 0.2, 0.5, 1.0, 1.5, float('inf')]
    labels = [
        '소멸고위험 (<0.2)',
        '소멸위험 (0.2~0.5)',
        '주의 (0.5~1.0)',
        '보통 (1.0~1.5)',
        '소멸저위험 (≥1.5)'
    ]
    grouped['위험등급'] = pd.cut(grouped['소멸위험지수'], bins=bins, labels=labels, right=False)
    
    # 전체 지역명 결합
    grouped['지역명'] = grouped['시도'] + ' ' + grouped['시군구']
    
    return grouped

# 데이터 로딩
df_all = load_extinction_data()
geojson_data = load_geojson()

# 이용 가능한 연도 목록 추출
years = sorted(df_all['연도'].unique())
min_year, max_year = years[0], years[-1]

# ==========================================
# 3. 사이드바 구성 (연도 선택 컨트롤)
# ==========================================
st.sidebar.title("⚙️ 대시보드 설정")
st.sidebar.markdown("---")

# 연도 선택 슬라이더
selected_year = st.sidebar.slider(
    "📅 분석 연도 선택",
    min_value=int(min_year),
    max_value=int(max_year),
    value=int(max_year),
    step=1
)

st.sidebar.markdown("---")
st.sidebar.info(
    "💡 **지방소멸위험지수란?**\n\n"
    "**`20~39세 여성 인구` ÷ `65세 이상 인구`**\n\n"
    "- **0.5 미만**: 소멸위험지역\n"
    "- **0.2 미만**: 소멸고위험지역\n\n"
    "지수가 낮을수록 인구 감소 및 지자체 소멸 위험이 높음을 의미합니다."
)

# 선택된 연도 데이터 필터링
df_year = df_all[df_all['연도'] == selected_year].copy()

# ==========================================
# 4. 메인 화면 - 헤더 및 핵심 요약 지표
# ==========================================
st.title("🚨 전국 지방소멸 위험지수 타임랩스 대시보드")
st.caption(f"2015년부터 {max_year}년까지 시군구별 소멸위험지수의 변화를 추적합니다.")
st.markdown("---")

# 선택 연도의 요약 통계 계산
total_sigungu = len(df_year)
danger_sigungu = len(df_year[df_year['소멸위험지수'] < 0.5])
high_danger_sigungu = len(df_year[df_year['소멸위험지수'] < 0.2])
avg_index = df_year['소멸위험지수'].mean()

# 지표 카드 4개 배치
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("선택 연도", f"{selected_year}년")
col_m2.metric("전국 평균 소멸위험지수", f"{avg_index:.3f}")
col_m3.metric(
    "소멸위험 이하 시군구 (<0.5)",
    f"{danger_sigungu}개",
    delta=f"전체의 {danger_sigungu / total_sigungu * 100:.1f}%",
    delta_color="inverse"
)
col_m4.metric(
    "소멸고위험 시군구 (<0.2)",
    f"{high_danger_sigungu}개",
    delta=f"전체의 {high_danger_sigungu / total_sigungu * 100:.1f}%",
    delta_color="inverse"
)

st.markdown("---")

# ==========================================
# 5. 단계구분도 지도 시각화
# ==========================================
st.subheader(f"🗺️ {selected_year}년 전국 시군구별 소멸위험 지도")

# 위험 단계별 색상 정의 (위험할수록 짙은 붉은색, 안전할수록 파란색)
color_map = {
    '소멸고위험 (<0.2)': '#BD0026',    # 진한 붉은색
    '소멸위험 (0.2~0.5)': '#F03B20',   # 주황빛 붉은색
    '주의 (0.5~1.0)': '#FEB24C',     # 황토/주황색
    '보통 (1.0~1.5)': '#74A9CF',     # 연한 파란색
    '소멸저위험 (≥1.5)': '#0570B0'    # 진한 파란색
}

category_order = [
    '소멸고위험 (<0.2)',
    '소멸위험 (0.2~0.5)',
    '주의 (0.5~1.0)',
    '보통 (1.0~1.5)',
    '소멸저위험 (≥1.5)'
]

fig_map = px.choropleth(
    df_year,
    geojson=geojson_data,
    locations='sigungu_code',
    featureidkey="properties.코드",
    color='위험등급',
    color_discrete_map=color_map,
    category_orders={'위험등급': category_order},
    hover_name='지역명',
    hover_data={
        'sigungu_code': False,
        '시도': True,
        '시군구': True,
        '소멸위험지수': ':.3f',
        '여성_20_39': ':,',
        '고령인구_65': ':,',
        '총인구': ':,',
        '위험등급': False
    },
    labels={
        '시도': '시/도',
        '시군구': '시/군/구',
        '소멸위험지수': '소멸위험지수',
        '여성_20_39': '20~39세 여성인구(명)',
        '고령인구_65': '65세 이상 인구(명)',
        '총인구': '총인구(명)',
        '위험등급': '위험 등급'
    }
)

# 타일 배경 숨기기 및 여백 조정
fig_map.update_geos(fitbounds="locations", visible=False)
fig_map.update_layout(
    margin={"r": 0, "t": 10, "l": 0, "b": 0},
    legend_title_text="소멸위험 등급",
    height=650
)

st.plotly_chart(fig_map, use_container_width=True)

st.markdown("---")

# ==========================================
# 6. 상위 / 하위 10개 지역 표 출력
# ==========================================
col_left, col_right = st.columns(2)

# 소멸위험지수가 가장 낮은 10곳 (가장 위험한 곳)
bottom10 = df_year.sort_values(by='소멸위험지수', ascending=True).head(10)[
    ['시도', '시군구', '소멸위험지수', '여성_20_39', '고령인구_65', '총인구']
].reset_index(drop=True)
bottom10.index = bottom10.index + 1

# 소멸위험지수가 가장 높은 10곳 (가장 안전한/젊은 곳)
top10 = df_year.sort_values(by='소멸위험지수', ascending=False).head(10)[
    ['시도', '시군구', '소멸위험지수', '여성_20_39', '고령인구_65', '총인구']
].reset_index(drop=True)
top10.index = top10.index + 1

with col_left:
    st.markdown(f"### 🔴 {selected_year}년 소멸위험 가장 심각한 지역 TOP 10")
    st.dataframe(
        bottom10,
        use_container_width=True,
        column_config={
            "소멸위험지수": st.column_config.NumberColumn("소멸위험지수", format="%.3f"),
            "여성_20_39": st.column_config.NumberColumn("20-39세 여성", format="%'d 명"),
            "고령인구_65": st.column_config.NumberColumn("65세 이상", format="%'d 명"),
            "총인구": st.column_config.NumberColumn("총인구", format="%'d 명"),
        }
    )

with col_right:
    st.markdown(f"### 🔵 {selected_year}년 소멸위험 가장 낮은(젊은) 지역 TOP 10")
    st.dataframe(
        top10,
        use_container_width=True,
        column_config={
            "소멸위험지수": st.column_config.NumberColumn("소멸위험지수", format="%.3f"),
            "여성_20_39": st.column_config.NumberColumn("20-39세 여성", format="%'d 명"),
            "고령인구_65": st.column_config.NumberColumn("65세 이상", format="%'d 명"),
            "총인구": st.column_config.NumberColumn("총인구", format="%'d 명"),
        }
    )

st.markdown("---")

# ==========================================
# 7. 연도별 소멸위험 지역 확산 시계열 차트
# ==========================================
st.subheader("📈 연도별 소멸위험 지역(지수 < 0.5) 증가 추이")

# 각 연도별 위험지역 수 집계
trend_df = df_all.groupby('연도').apply(
    lambda x: pd.Series({
        '소멸위험_지역수': (x['소멸위험지수'] < 0.5).sum(),
        '소멸고위험_지역수': (x['소멸위험지수'] < 0.2).sum(),
        '전체_시군구수': len(x)
    })
).reset_index()

trend_df['소멸위험_비율'] = (trend_df['소멸위험_지역수'] / trend_df['전체_시군구수']) * 100

# Plotly 선 그래프 생성
fig_trend = go.Figure()

fig_trend.add_trace(go.Scatter(
    x=trend_df['연도'],
    y=trend_df['소멸위험_지역수'],
    mode='lines+markers+text',
    name='소멸위험 이하 (<0.5)',
    text=[f"{val}개" for val in trend_df['소멸위험_지역수']],
    textposition="top center",
    line=dict(color='#F03B20', width=3),
    marker=dict(size=8)
))

fig_trend.add_trace(go.Scatter(
    x=trend_df['연도'],
    y=trend_df['소멸고위험_지역수'],
    mode='lines+markers+text',
    name='소멸고위험 (<0.2)',
    text=[f"{val}개" for val in trend_df['소멸고위험_지역수']],
    textposition="bottom center",
    line=dict(color='#BD0026', width=3, dash='dash'),
    marker=dict(size=8)
))

# 현재 선택된 연도 강조 표시 라인
fig_trend.add_vline(
    x=selected_year,
    line_width=2,
    line_dash="dot",
    line_color="gray",
    annotation_text=f"현재 선택: {selected_year}년",
    annotation_position="top left"
)

fig_trend.update_layout(
    xaxis=dict(title="연도", tickmode='linear'),
    yaxis=dict(title="시군구 수 (개)"),
    height=400,
    margin=dict(l=20, r=20, t=30, b=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
)

st.plotly_chart(fig_trend, use_container_width=True)

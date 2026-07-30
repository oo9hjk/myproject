import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import re

# ==========================================
# 1. 스트림릿 페이지 기본 설정
# ==========================================
st.set_page_config(
    page_title="전국 시군구별 고령화 지도",
    page_icon="🗺️",
    layout="wide"
)

# ==========================================
# 2. 데이터 로딩 및 전처리 함수
# ==========================================

# 지도 경계선 GeoJSON 데이터 불러오기
@st.cache_data
def load_geojson():
    geojson_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"
    response = requests.get(geojson_url)
    return response.json()

# 인구 CSV 데이터 불러오기 및 고령화율 계산하기
@st.cache_data
def load_population_data():
    csv_url = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
    
    # '코드' 열은 숫자가 아닌 문자열로 읽어 앞자리 0이 사라지지 않게 처리합니다.
    df = pd.read_csv(csv_url, compression='gzip', dtype={'코드': str})
    
    # 혹시 모를 자릿수 손실을 방지하기 위해 10자리 문자열로 맞춥니다.
    df['코드'] = df['코드'].astype(str).str.zfill(10)
    
    # 1. 가장 최신 연도 데이터만 추출
    latest_year = df['연도'].max()
    df_latest = df[df['연도'] == latest_year].copy()
    
    # 2. 행정동 코드 앞 5자리를 잘라 시군구 코드 생성
    df_latest['sigungu_code'] = df_latest['코드'].str[:5]
    
    # 3. 전체 인구 열('계_')과 65세 이상 인구 열 추출
    total_cols = [col for col in df_latest.columns if col.startswith('계_')]
    
    age65_cols = []
    for col in total_cols:
        # 열 이름에서 숫자(나이)만 추출
        match = re.search(r'\d+', col)
        if match and int(match.group()) >= 65:
            age65_cols.append(col)
            
    # 4. 읍·면·동 단위 인구를 행정동에서 합산
    df_latest['읍면동_총인구'] = df_latest[total_cols].sum(axis=1)
    df_latest['읍면동_고령인구'] = df_latest[age65_cols].sum(axis=1)
    
    # 5. 시군구 코드(5자리) 기준으로 그룹화하여 합산
    grouped = df_latest.groupby('sigungu_code').agg(
        시도=('시도', 'first'),
        시군구=('시군구', 'first'),
        총인구=('읍면동_총인구', 'sum'),
        고령인구=('읍면동_고령인구', 'sum')
    ).reset_index()
    
    # 6. 고령화율 계산 (%)
    grouped['고령화율'] = (grouped['고령인구'] / grouped['총인구']) * 100
    grouped['고령화율'] = grouped['고령화율'].round(2)
    
    # 7. 5단계 구간으로 나누기 (경계값: 19%, 23%, 28%, 38%)
    bins = [-float('inf'), 19, 23, 28, 38, float('inf')]
    labels = ['19% 미만', '19% ~ 23% 미만', '23% ~ 28% 미만', '28% ~ 38% 미만', '38% 이상']
    grouped['고령화율_구간'] = pd.cut(grouped['고령화율'], bins=bins, labels=labels, right=False)
    
    # 마우스 오버용 전체 지역명 추가
    grouped['지역명'] = grouped['시도'] + ' ' + grouped['시군구']
    
    return grouped, latest_year

# 데이터 로드 실행
grouped_df, latest_year = load_population_data()
geojson_data = load_geojson()


# ==========================================
# 3. 메인 화면 구성
# ==========================================
st.title("🗺️ 대한민국 시군구별 고령화 지도")
st.subheader(f"가장 최근 데이터인 {latest_year}년 기준 65세 이상 고령 인구 비율입니다.")
st.markdown("---")

# 5단계 범례 색상 지정 (연한 색 -> 진한 색)
color_map = {
    '19% 미만': '#FEF0D9',
    '19% ~ 23% 미만': '#FDCC8A',
    '23% ~ 28% 미만': '#FC8D59',
    '28% ~ 38% 미만': '#E34A33',
    '38% 이상': '#B30000'
}

# Plotly 시각화 지도 생성
fig = px.choropleth(
    grouped_df,
    geojson=geojson_data,
    locations='sigungu_code',
    featureidkey="properties.코드",   # GeoJSON의 5자리 코드와 연결
    color='고령화율_구간',
    color_discrete_map=color_map,
    category_orders={
        '고령화율_구간': ['19% 미만', '19% ~ 23% 미만', '23% ~ 28% 미만', '28% ~ 38% 미만', '38% 이상']
    },
    hover_name='지역명',
    hover_data={
        'sigungu_code': False,
        '시도': True,
        '시군구': True,
        '고령화율': ':.2f%',
        '총인구': ':,',
        '고령인구': ':,',
        '고령화율_구간': False
    },
    labels={
        '시도': '시/도',
        '시군구': '시/군/구',
        '고령화율': '고령화율(%)',
        '총인구': '총인구(명)',
        '고령인구': '65세 이상 인구(명)',
        '고령화율_구간': '고령화율 구간'
    }
)

# 배경 타일을 없애고 경계선만 깔끔하게 표시
fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(
    margin={"r": 0, "t": 10, "l": 0, "b": 0},
    legend_title_text="고령화 비율 구간",
    height=650
)

# 지도 화면 출력
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ==========================================
# 4. 고령화율 상위 / 하위 10개 지역 표 출력
# ==========================================
col1, col2 = st.columns(2)

# 고령화율 높은 순 상위 10개
top10_high = grouped_df.sort_values(by='고령화율', ascending=False).head(10)[
    ['시도', '시군구', '총인구', '고령인구', '고령화율']
].reset_index(drop=True)
top10_high.index = top10_high.index + 1

# 고령화율 낮은 순 상위 10개
top10_low = grouped_df.sort_values(by='고령화율', ascending=True).head(10)[
    ['시도', '시군구', '총인구', '고령인구', '고령화율']
].reset_index(drop=True)
top10_low.index = top10_low.index + 1

with col1:
    st.markdown("### 🔴 고령화율 가장 높은 지역 TOP 10")
    st.dataframe(
        top10_high,
        use_container_width=True,
        column_config={
            "총인구": st.column_config.NumberColumn("총인구", format="%'d 명"),
            "고령인구": st.column_config.NumberColumn("65세 이상 인구", format="%'d 명"),
            "고령화율": st.column_config.NumberColumn("고령화율", format="%.2f %%"),
        }
    )

with col2:
    st.markdown("### 🔵 고령화율 가장 낮은 지역 TOP 10")
    st.dataframe(
        top10_low,
        use_container_width=True,
        column_config={
            "총인구": st.column_config.NumberColumn("총인구", format="%'d 명"),
            "고령인구": st.column_config.NumberColumn("65세 이상 인구", format="%'d 명"),
            "고령화율": st.column_config.NumberColumn("고령화율", format="%.2f %%"),
        }
    )

const palette = ['#387957', '#88aa69', '#e1b15e', '#577f73', '#9f765c', '#b3c8a0']
const axis = { axisLine: { lineStyle: { color: '#dce4db' } }, axisTick: { show: false } }
const numberAxis = { ...axis, splitLine: { lineStyle: { color: '#e9efe7' } } }

export function toChartOptions({ labels, values, unit, type, horizontal = false, max }) {
  const tooltip = { trigger: type === 'pie' ? 'item' : 'axis', valueFormatter: (value) => `${value} ${unit}` }
  if (type === 'pie') {
    return {
      color: palette, tooltip,
      legend: { bottom: 0, type: 'scroll', textStyle: { color: '#4d5d52' } },
      series: [{
        type, radius: ['46%', '73%'], center: ['50%', '43%'], label: { show: false },
        avoidLabelOverlap: true, itemStyle: { borderWidth: 3, borderColor: '#fff', borderRadius: 5 },
        data: labels.map((name, index) => ({ name, value: values[index] })),
      }],
    }
  }
  const isTrend = type === 'line'
  const categories = { ...axis, type: 'category', data: labels, axisLabel: { width: 78, overflow: 'truncate' } }
  const numeric = {
    ...numberAxis, type: 'value', name: unit, nameTextStyle: { color: '#536258' },
    max: isTrend ? ({ max: peak }) => Math.max(Math.ceil(peak * 1.15), 1) : max,
  }
  return {
    color: palette, tooltip, animation: !isTrend,
    grid: { top: 34, left: 14, bottom: 7, right: 20, containLabel: true },
    xAxis: horizontal ? numeric : categories,
    yAxis: horizontal ? { ...categories, inverse: true } : numeric,
    series: isTrend
      ? [{ type, data: values, smooth: true, showSymbol: true, symbol: 'circle', symbolSize: 8,
           areaStyle: { color: 'rgba(68, 130, 93, .12)' } }]
      : [{ type, data: values, barMaxWidth: 28, itemStyle: { borderRadius: horizontal ? [0, 5, 5, 0] : [5, 5, 0, 0] } }],
  }
}

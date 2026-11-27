window.SB_VIEWS = window.SB_VIEWS || {};
window.SB_VIEWS["screens-view"] = {
  template: `
  <div class="panel">
    <h2>屏幕台账</h2>
    <p class="lead">物理终端绑定分区、分辨率与在线状态；室外屏正式发布须绑布局。</p>
    <table>
      <thead><tr><th>编码</th><th>标题</th><th>分区</th><th>分辨率</th><th>状态</th><th>风险</th><th>正式布局</th></tr></thead>
      <tbody>
        <tr v-for="s in items" :key="s.id">
          <td>{{ s.code }}</td><td>{{ s.title }}</td><td>{{ s.zone_title }}</td>
          <td>{{ s.resolution }}</td>
          <td><span class="badge" :class="s.status==='online'?'':(s.status==='maintenance'?'bad':'warn')">{{ s.status_label }}</span></td>
          <td>{{ s.risk_level }}</td>
          <td>
            <span v-if="s.publication_id && s.layout_code">{{ s.layout_code }}</span>
            <span class="badge bad" v-else-if="s.layout_gap">缺布局</span>
            <span class="hint" v-else>未发布</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>`,
  data() { return { items: [] }; },
  async mounted() { this.items = (await SB.api("/api/screens")).items; }
};

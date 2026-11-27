window.SB_VIEWS = window.SB_VIEWS || {};
window.SB_VIEWS["history-view"] = {
  template: `
  <div>
    <div class="panel">
      <h2>变更历史</h2>
      <p class="lead">发布、撤屏、覆盖与台账变更同源可追溯。</p>
      <table>
        <thead><tr><th>ID</th><th>实体</th><th>动作</th><th>详情</th><th>操作者</th></tr></thead>
        <tbody>
          <tr v-for="h in items" :key="h.id">
            <td>{{ h.id }}</td><td>{{ h.entity_kind }}#{{ h.entity_id }}</td>
            <td>{{ h.action }}</td><td>{{ h.detail }}</td><td>{{ h.actor }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel">
      <h3>互斥争用痕</h3>
      <p class="lead">室外屏布局绑定互斥下，后到者只留痕，不落正式行。</p>
      <table>
        <thead><tr><th>ID</th><th>资源</th><th>持锁</th><th>后到</th><th>动作</th></tr></thead>
        <tbody>
          <tr v-for="c in contentions" :key="c.id">
            <td>{{ c.id }}</td><td>{{ c.lock_key }}（屏#{{ c.screen_id }}）</td>
            <td>{{ c.holder }}</td><td>{{ c.contender }}</td><td>{{ c.action }}</td>
          </tr>
          <tr v-if="!contentions.length"><td colspan="5" class="hint">暂无争用</td></tr>
        </tbody>
      </table>
    </div>
  </div>`,
  data() { return { items: [], contentions: [] }; },
  async mounted() {
    const d = await SB.api("/api/history");
    this.items = d.items;
    this.contentions = d.contentions || [];
  }
};


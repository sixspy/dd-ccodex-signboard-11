window.SB_VIEWS = window.SB_VIEWS || {};
window.SB_VIEWS["dashboard-view"] = {
  template: `
  <div>
    <div class="panel">
      <h2>总览</h2>
      <p class="lead">{{ meta.skeleton || "加载中…" }}</p>
      <div class="stats">
        <div class="stat" v-for="s in cards" :key="s.k"><b>{{ s.v }}</b><span>{{ s.l }}</span></div>
      </div>
      <p class="badge" :class="meta.outdoor_layout_ready ? '' : 'bad'" v-if="meta.outdoor_publications">
        室外齐套：{{ meta.outdoor_layout_ready ? "已齐套" : "未齐套" }} ·
        室外正式发布 {{ meta.outdoor_publications }} 条，缺布局 {{ meta.outdoor_unbound_publications }} 条
      </p>
    </div>
  </div>`,
  data() { return { meta: {}, cards: [] }; },
  async mounted() {
    const d = await SB.api("/api/dashboard");
    this.meta = d;
    this.cards = [
      { k: "screens", l: "屏幕总数", v: d.screens },
      { k: "online", l: "在线屏幕", v: d.online_screens },
      { k: "assets", l: "可播素材", v: d.ready_assets },
      { k: "pubs", l: "正式发布", v: d.official_publications },
      { k: "shadows", l: "待升正影子", v: d.open_shadows },
      { k: "outdoor", l: "室外正式发布", v: d.outdoor_publications },
      { k: "unbound", l: "室外缺布局", v: d.outdoor_unbound_publications },
      { k: "race", l: "互斥争用痕", v: d.lock_contentions },
      { k: "ov", l: "生效覆盖", v: d.active_overrides },
    ];
  }
};

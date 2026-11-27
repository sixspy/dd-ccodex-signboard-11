window.SB_VIEWS = window.SB_VIEWS || {};
window.SB_VIEWS["layouts-view"] = {
  template: `
  <div>
    <div class="panel">
      <h2>屏幕布局</h2>
      <p class="lead">多区画布槽位，发布时须绑定；室外屏正式发布缺布局整笔拒写。</p>
      <div class="row-form">
        <input v-model="form.code" placeholder="编码，如 lay_split" />
        <input v-model="form.title" placeholder="布局标题" />
        <input v-model.number="form.slotCount" type="number" min="1" max="6" placeholder="槽位数" />
        <button class="primary" @click="create">新建布局</button>
      </div>
      <p class="err" v-if="error">{{ error }}</p>
      <p class="hint" v-if="msg">{{ msg }}</p>
    </div>
    <div class="panel" v-for="l in items" :key="l.id">
      <h3>{{ l.code }} · {{ l.title }}
        <span class="badge" v-if="l.bound">被 {{ l.publication_count }} 条正式发布占用</span>
        <span class="badge warn" v-else>暂未被发布绑定</span>
      </h3>
      <div class="slot-canvas">
        <div class="slot" v-for="s in l.slots" :key="s.name"
             :style="{ left: s.x + '%', top: s.y + '%', width: s.w + '%', height: s.h + '%' }">
          {{ s.name }}
        </div>
      </div>
      <p class="hint">{{ l.slot_count }} 个槽位{{ l.note ? " · " + l.note : "" }}</p>
    </div>
  </div>`,
  data() {
    return { items: [], error: "", msg: "", form: { code: "", title: "", slotCount: 2 } };
  },
  async mounted() { await this.reload(); },
  methods: {
    async reload() { this.items = (await SB.api("/api/layouts")).items; },
    async create() {
      this.error = ""; this.msg = "";
      const n = Math.max(1, Math.min(6, this.form.slotCount || 1));
      const slots = n === 1
        ? [{ name: "main", x: 0, y: 0, w: 100, h: 100 }]
        : Array.from({ length: n }, (_, i) => ({
            name: "slot" + (i + 1),
            x: 0,
            y: Math.round((i * 100) / n),
            w: 100,
            h: Math.round(100 / n),
          }));
      try {
        await SB.api("/api/layouts", {
          method: "POST",
          body: JSON.stringify({ code: this.form.code, title: this.form.title, slots })
        });
        this.msg = "布局已创建";
        this.form = { code: "", title: "", slotCount: 2 };
        await this.reload();
      } catch (e) { this.error = e.message; }
    }
  }
};

/**
 * 心理健康AI助手 - 主逻辑
 */

(function () {
  'use strict';

  // ====== DOM 元素 ======
  var sidebar = document.getElementById('sidebar');
  var sidebarToggle = document.getElementById('sidebarToggle');
  var navItems = document.querySelectorAll('.nav-item');
  var pageTitle = document.getElementById('pageTitle');
  var content = document.getElementById('content');

  // ====== Chart 实例引用（切换页面时销毁） ======
  var chartInstances = [];

  // ====== 用户状态 ======
  var currentUser = null;

  function loadUserFromStorage() {
    try {
      var raw = localStorage.getItem('mh_user');
      var expiry = localStorage.getItem('mh_expiry');
      if (raw && expiry && Date.now() < parseInt(expiry)) {
        currentUser = JSON.parse(raw);
      } else {
        localStorage.removeItem('mh_user');
        localStorage.removeItem('mh_expiry');
        currentUser = null;
      }
    } catch (e) { currentUser = null; }
    updateUserUI();
  }

  function saveUser(user, remember) {
    currentUser = user;
    localStorage.setItem('mh_user', JSON.stringify(user));
    if (remember) {
      localStorage.setItem('mh_expiry', Date.now() + 30 * 24 * 3600 * 1000);
    } else {
      localStorage.setItem('mh_expiry', Date.now() + 24 * 3600 * 1000);
    }
    updateUserUI();
  }

  function logout() {
    currentUser = null;
    localStorage.removeItem('mh_user');
    localStorage.removeItem('mh_expiry');
    updateUserUI();
  }

  function updateUserUI() {
    var guestTrigger = document.getElementById('userTriggerGuest');
    var loggedTrigger = document.getElementById('userTriggerLogged');
    var dropdownGuest = document.getElementById('dropdownGuest');
    var dropdownLogged = document.getElementById('dropdownLogged');

    if (currentUser) {
      if (guestTrigger) guestTrigger.style.display = 'none';
      if (loggedTrigger) loggedTrigger.style.display = 'flex';
      if (dropdownGuest) dropdownGuest.style.display = 'none';
      if (dropdownLogged) dropdownLogged.style.display = 'block';
      var avatar = document.getElementById('userAvatar');
      var nick = document.getElementById('userNickname');
      if (avatar) avatar.textContent = currentUser.nickname.charAt(0).toUpperCase();
      if (nick) nick.textContent = currentUser.nickname;
    } else {
      if (guestTrigger) guestTrigger.style.display = 'flex';
      if (loggedTrigger) loggedTrigger.style.display = 'none';
      if (dropdownGuest) dropdownGuest.style.display = 'block';
      if (dropdownLogged) dropdownLogged.style.display = 'none';
    }
  }

  function currentUserId() {
    return currentUser && currentUser.id ? currentUser.id : 1;
  }

  function jsonHeaders() {
    var headers = { 'Content-Type': 'application/json' };
    if (currentUser && currentUser.token) {
      headers.Authorization = 'Bearer ' + currentUser.token;
    }
    return headers;
  }

  // ====== 侧边栏展开/收起 ======
  var sidebarCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
  if (sidebarCollapsed) {
    sidebar.classList.add('collapsed');
  }

  sidebarToggle.addEventListener('click', function () {
    sidebar.classList.toggle('collapsed');
    var isCollapsed = sidebar.classList.contains('collapsed');
    localStorage.setItem('sidebarCollapsed', isCollapsed);
  });

  // ====== 登录/注册弹窗 ======
  function showModal(id) { document.getElementById(id).style.display = 'flex'; }
  function hideModal(id) { document.getElementById(id).style.display = 'none'; }

  document.querySelectorAll('[data-close]').forEach(function (btn) {
    btn.addEventListener('click', function () { hideModal(this.dataset.close); });
  });
  document.querySelectorAll('.modal-overlay').forEach(function (m) {
    m.addEventListener('click', function (e) { if (e.target === m) m.style.display = 'none'; });
  });

  document.getElementById('btnShowLogin').addEventListener('click', function () {
    document.getElementById('userMenu').classList.remove('open');
    showModal('loginModal');
  });
  document.getElementById('btnShowRegister').addEventListener('click', function () {
    document.getElementById('userMenu').classList.remove('open');
    showModal('registerModal');
  });
  document.getElementById('btnLogout').addEventListener('click', function () {
    document.getElementById('userMenu').classList.remove('open');
    logout();
  });
  document.getElementById('btnProfile').addEventListener('click', function () {
    document.getElementById('userMenu').classList.remove('open');
    if (!currentUser) { showModal('loginModal'); return; }
    showInfoModal(
      '个人信息',
      '<div class="detail-grid">' +
        '<span>用户ID</span><strong>#' + currentUser.id + '</strong>' +
        '<span>昵称</span><strong>' + escapeHtml(currentUser.nickname || '') + '</strong>' +
        '<span>手机号</span><strong>' + escapeHtml(currentUser.phone || '未填写') + '</strong>' +
      '</div>'
    );
  });
  document.getElementById('btnSettings').addEventListener('click', function () {
    document.getElementById('userMenu').classList.remove('open');
    showInfoModal(
      '设置',
      '<div class="settings-list">' +
        '<button class="btn btn-default" id="settingToggleSidebar">' + (sidebar.classList.contains('collapsed') ? '展开侧边栏' : '收起侧边栏') + '</button>' +
        '<button class="btn btn-default" id="settingClearSession">清除本地登录状态</button>' +
      '</div>'
    );
    document.getElementById('settingToggleSidebar').addEventListener('click', function () {
      sidebar.classList.toggle('collapsed');
      localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
      hideInfoModal();
    });
    document.getElementById('settingClearSession').addEventListener('click', function () {
      logout();
      hideInfoModal();
    });
  });

  // 登录提交
  document.getElementById('btnLoginSubmit').addEventListener('click', function () {
    var nick = document.getElementById('loginNickname').value.trim();
    var pass = document.getElementById('loginPassword').value.trim();
    var remember = document.getElementById('loginRemember').checked;
    var errEl = document.getElementById('loginError');
    errEl.style.display = 'none';

    if (!nick || !pass) { errEl.textContent = '请填写昵称和密码'; errEl.style.display = 'block'; return; }

    fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname: nick, password: pass, remember_me: remember }),
    })
      .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, data: d }; }); })
      .then(function (r) {
        if (!r.ok) { errEl.textContent = r.data.detail || '登录失败'; errEl.style.display = 'block'; return; }
        saveUser(Object.assign({}, r.data.user, { token: r.data.token }), remember);
        hideModal('loginModal');
        document.getElementById('loginNickname').value = '';
        document.getElementById('loginPassword').value = '';
      })
      .catch(function () { errEl.textContent = '网络错误，请重试'; errEl.style.display = 'block'; });
  });

  // 发送验证码
  var codeSending = false;
  document.getElementById('btnSendCode').addEventListener('click', function () {
    if (codeSending) return;
    var phone = document.getElementById('regPhone').value.trim();
    if (!phone) { alert('请先填写手机号'); return; }
    codeSending = true;
    var btn = this;
    btn.textContent = '发送中...';
    fetch('/api/auth/send-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: phone }),
    })
      .then(function (res) {
        return res.json().then(function (data) { return { ok: res.ok, data: data }; });
      })
      .then(function (result) {
        if (!result.ok) throw new Error(result.data.detail || '发送失败');
        var hint = document.getElementById('codeHint');
        hint.textContent = result.data.dev_code
          ? '本地开发验证码：' + result.data.dev_code
          : '验证码已通过短信发送，请注意查收。';
        hint.style.display = 'block';
        btn.textContent = '已发送';
        setTimeout(function () { codeSending = false; btn.textContent = '获取验证码'; }, 60000);
      })
      .catch(function (err) {
        codeSending = false;
        btn.textContent = '获取验证码';
        var hint = document.getElementById('codeHint');
        hint.textContent = err.message || '验证码发送失败，请稍后重试';
        hint.style.display = 'block';
      });
  });

  // 注册提交
  document.getElementById('btnRegisterSubmit').addEventListener('click', function () {
    var nick = document.getElementById('regNickname').value.trim();
    var phone = document.getElementById('regPhone').value.trim();
    var code = document.getElementById('regCode').value.trim();
    var pass = document.getElementById('regPassword').value.trim();
    var errEl = document.getElementById('regError');
    errEl.style.display = 'none';

    if (!nick) { errEl.textContent = '请设置昵称'; errEl.style.display = 'block'; return; }
    if (!phone) { errEl.textContent = '请填写手机号'; errEl.style.display = 'block'; return; }
    if (!code) { errEl.textContent = '请填写验证码'; errEl.style.display = 'block'; return; }
    if (!pass || pass.length < 6) { errEl.textContent = '密码至少6位'; errEl.style.display = 'block'; return; }

    fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname: nick, phone: phone, code: code, password: pass }),
    })
      .then(function (res) { return res.json().then(function (d) { return { ok: res.ok, data: d }; }); })
      .then(function (r) {
        if (!r.ok) { errEl.textContent = r.data.detail || '注册失败'; errEl.style.display = 'block'; return; }
        alert('注册成功！请登录');
        hideModal('registerModal');
        document.getElementById('regNickname').value = '';
        document.getElementById('regPhone').value = '';
        document.getElementById('regCode').value = '';
        document.getElementById('regPassword').value = '';
        document.getElementById('codeHint').style.display = 'none';
        showModal('loginModal');
      })
      .catch(function () { errEl.textContent = '网络错误，请重试'; errEl.style.display = 'block'; });
  });

  // ====== 用户菜单切换（已登录/未登录共用） ======
  var userMenu = document.getElementById('userMenu');
  document.getElementById('userTriggerGuest').addEventListener('click', function (e) {
    e.stopPropagation();
    userMenu.classList.toggle('open');
  });
  document.getElementById('userTriggerLogged').addEventListener('click', function (e) {
    e.stopPropagation();
    userMenu.classList.toggle('open');
  });
  document.addEventListener('click', function () { userMenu.classList.remove('open'); });

  // ====== 初始化用户状态 ======
  loadUserFromStorage();

  // ====== 页面配置 ======
  var pageConfig = {
    analytics: {
      title: '数据分析',
      render: renderAnalytics,
      onReady: loadAnalyticsData,
    },
    articles: {
      title: '知识文章',
      render: renderArticles,
      onReady: loadArticles,
    },
    records: {
      title: '咨询记录',
      render: renderRecords,
      onReady: loadRecords,
    },
    mood: {
      title: '情绪日志',
      render: renderMood,
      onReady: loadMood,
    },
    community: {
      title: '社区讨论',
      render: renderCommunity,
      onReady: loadCommunity,
    },
    consult: {
      title: '咨询入口',
      render: renderConsult,
      onReady: initConsult,
    },
  };

  var API_BASE = '/api';

  // ====== 工具函数 ======

  function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function shortDate(isoStr) {
    var parts = isoStr.split('-');
    return parts[1] + '/' + parts[2];
  }

  function destroyCharts() {
    chartInstances.forEach(function (c) {
      if (c && typeof c.destroy === 'function') c.destroy();
    });
    chartInstances = [];
  }

  // ====== 渲染函数 ======

  /**
   * 知识文章页 — 搜索栏 + 发布按钮 + 文章列表 + 弹窗
   */
  function renderArticles() {
    return (
      // 搜索栏
      '<div class="search-bar">' +
        '<div class="search-fields">' +
          '<div class="search-field">' +
            '<label class="search-label">文章标题</label>' +
            '<input type="text" class="search-input" id="sTitle" placeholder="输入文章标题关键词" />' +
          '</div>' +
          '<div class="search-field">' +
            '<label class="search-label">分类</label>' +
            '<input type="text" class="search-input" id="sCategory" placeholder="输入分类名称" />' +
          '</div>' +
          '<div class="search-field">' +
            '<label class="search-label">状态</label>' +
            '<select class="search-input" id="sStatus">' +
              '<option value="">全部</option>' +
              '<option value="已发布">已发布</option>' +
              '<option value="草稿">草稿</option>' +
            '</select>' +
          '</div>' +
        '</div>' +
        '<div class="search-actions">' +
          '<button class="btn btn-primary" id="btnSearch">查询</button>' +
          '<button class="btn btn-default" id="btnReset">重置</button>' +
          '<button class="btn btn-success" id="btnPublish">+ 发布文章</button>' +
        '</div>' +
      '</div>' +
      // 文章列表
      '<div class="article-list" id="articleList">' +
        '<p class="article-list-hint">加载中...</p>' +
      '</div>' +
      // 发布文章弹窗
      '<div class="modal-overlay" id="publishModal" style="display:none;">' +
        '<div class="modal">' +
          '<div class="modal-header">' +
            '<h2 class="modal-title" id="articleModalTitle">发布文章</h2>' +
            '<button class="modal-close" id="modalClose">&times;</button>' +
          '</div>' +
          '<div class="modal-body">' +
            '<input type="hidden" id="pArticleId" />' +
            '<div class="form-group">' +
              '<label class="form-label">文章标题 <span class="required">*</span></label>' +
              '<input type="text" class="form-input" id="pTitle" placeholder="请输入文章标题" />' +
            '</div>' +
            '<div class="form-group">' +
              '<label class="form-label">所属分类 <span class="required">*</span></label>' +
              '<div class="category-input-wrap">' +
                '<input type="text" class="form-input" id="pCategory" list="categoryList" placeholder="选择或输入分类" />' +
                '<datalist id="categoryList"></datalist>' +
              '</div>' +
            '</div>' +
            '<div class="form-group">' +
              '<label class="form-label">作者</label>' +
              '<input type="text" class="form-input" id="pAuthor" placeholder="默认使用当前昵称" />' +
            '</div>' +
            '<div class="form-group">' +
              '<label class="form-label">文章摘要</label>' +
              '<input type="text" class="form-input" id="pSummary" placeholder="可选，简要描述文章内容" />' +
            '</div>' +
            '<div class="form-group">' +
              '<label class="form-label">发布状态</label>' +
              '<select class="form-input" id="pStatus">' +
                '<option value="已发布">已发布</option>' +
                '<option value="草稿">草稿</option>' +
              '</select>' +
            '</div>' +
            '<div class="form-group">' +
              '<label class="form-label">封面图片</label>' +
              '<input type="text" class="form-input" id="pCover" placeholder="可选，输入图片URL地址" />' +
            '</div>' +
            '<div class="form-group">' +
              '<label class="form-label">文章内容 <span class="required">*</span></label>' +
              '<textarea class="form-textarea" id="pContent" rows="8" placeholder="请输入文章正文内容"></textarea>' +
            '</div>' +
          '</div>' +
          '<div class="modal-footer">' +
            '<button class="btn btn-default" id="modalCancel">取消</button>' +
            '<button class="btn btn-primary" id="modalSubmit">确认发布</button>' +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  function loadArticles() {
    doArticleSearch();

    document.getElementById('btnSearch').addEventListener('click', doArticleSearch);
    document.getElementById('btnReset').addEventListener('click', function () {
      document.getElementById('sTitle').value = '';
      document.getElementById('sCategory').value = '';
      document.getElementById('sStatus').value = '';
      doArticleSearch();
    });

    // 发布按钮 → 打开弹窗
    var modal = document.getElementById('publishModal');
    document.getElementById('btnPublish').addEventListener('click', function () {
      loadCategoryDatalist();
      resetArticleForm();
      modal.style.display = 'flex';
    });
    document.getElementById('modalClose').addEventListener('click', function () { modal.style.display = 'none'; });
    document.getElementById('modalCancel').addEventListener('click', function () { modal.style.display = 'none'; });
    modal.addEventListener('click', function (e) { if (e.target === modal) modal.style.display = 'none'; });

    // 提交
    document.getElementById('modalSubmit').addEventListener('click', submitArticle);
  }

  function loadCategoryDatalist() {
    var datalist = document.getElementById('categoryList');
    if (datalist.options.length > 0) return; // already loaded
    fetch(API_BASE + '/articles/categories')
      .then(function (res) { return res.json(); })
      .then(function (cats) {
        cats.forEach(function (c) {
          var opt = document.createElement('option');
          opt.value = c;
          datalist.appendChild(opt);
        });
      })
      .catch(function () {});
  }

  function submitArticle() {
    var articleId = document.getElementById('pArticleId').value;
    var title = document.getElementById('pTitle').value.trim();
    var author = document.getElementById('pAuthor').value.trim();
    var category = document.getElementById('pCategory').value.trim();
    var content = document.getElementById('pContent').value.trim();
    var summary = document.getElementById('pSummary').value.trim();
    var cover = document.getElementById('pCover').value.trim();
    var status = document.getElementById('pStatus').value;

    // 必填校验
    if (!title) { alert('请填写文章标题'); return; }
    if (!category) { alert('请选择或输入所属分类'); return; }
    if (!content) { alert('请填写文章内容'); return; }

    var payload = {
      title: title,
      author: author || (currentUser ? currentUser.nickname : '匿名'),
      category: category,
      content: content,
      summary: summary,
      cover_image: cover,
      status: status,
    };

    fetch(API_BASE + '/articles/' + (articleId ? articleId : ''), {
      method: articleId ? 'PATCH' : 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        if (!res.ok) throw new Error(articleId ? '保存失败' : '发布失败');
        return res.json();
      })
      .then(function () {
        // 关闭弹窗 + 清空表单 + 刷新列表
        document.getElementById('publishModal').style.display = 'none';
        resetArticleForm();
        doArticleSearch();
      })
      .catch(function (err) {
        alert(articleId ? '保存失败，请重试' : '发布失败，请重试');
        console.error(err);
      });
  }

  function resetArticleForm() {
    document.getElementById('articleModalTitle').textContent = '发布文章';
    document.getElementById('modalSubmit').textContent = '确认发布';
    document.getElementById('pArticleId').value = '';
    document.getElementById('pTitle').value = '';
    document.getElementById('pAuthor').value = currentUser ? currentUser.nickname : '';
    document.getElementById('pCategory').value = '';
    document.getElementById('pContent').value = '';
    document.getElementById('pSummary').value = '';
    document.getElementById('pCover').value = '';
    document.getElementById('pStatus').value = '已发布';
  }

  function openArticleEditor(id) {
    fetch(API_BASE + '/articles/' + id)
      .then(function (res) { if (!res.ok) throw new Error('load failed'); return res.json(); })
      .then(function (a) {
        loadCategoryDatalist();
        document.getElementById('articleModalTitle').textContent = '编辑文章';
        document.getElementById('modalSubmit').textContent = '保存修改';
        document.getElementById('pArticleId').value = a.id;
        document.getElementById('pTitle').value = a.title || '';
        document.getElementById('pAuthor').value = a.author || '';
        document.getElementById('pCategory').value = a.category || '';
        document.getElementById('pContent').value = a.content || '';
        document.getElementById('pSummary').value = a.summary || '';
        document.getElementById('pCover').value = a.cover_image || '';
        document.getElementById('pStatus').value = a.status || '已发布';
        document.getElementById('publishModal').style.display = 'flex';
      })
      .catch(function () { alert('加载文章失败'); });
  }

  function doArticleSearch() {
    var title = encodeURIComponent(document.getElementById('sTitle').value.trim());
    var category = encodeURIComponent(document.getElementById('sCategory').value.trim());
    var status = encodeURIComponent(document.getElementById('sStatus').value);
    var params = 'title=' + title + '&category=' + category + '&status=' + status;

    fetch(API_BASE + '/articles/?' + params)
      .then(function (res) { return res.json(); })
      .then(function (data) { renderArticleList(data); })
      .catch(function () {
        document.getElementById('articleList').innerHTML =
          '<p class="article-list-empty">加载失败，请重试</p>';
      });
  }

  function renderArticleList(articles) {
    var container = document.getElementById('articleList');
    if (!articles || articles.length === 0) {
      container.innerHTML = '<p class="article-list-empty">暂无匹配的文章</p>';
      return;
    }
    var html = '';
    articles.forEach(function (a) {
      var dateStr = a.created_at ? a.created_at.slice(0, 10) : '';
      var badgeClass = a.status === '草稿' ? 'badge-draft' : 'badge-published';
      html +=
        '<div class="article-card" data-id="' + a.id + '">' +
          '<div class="article-card-body">' +
            '<h3 class="article-card-title">' + escapeHtml(a.title) + '</h3>' +
            '<p class="article-card-summary">' + escapeHtml(truncate(a.content, 120)) + '</p>' +
          '</div>' +
          '<div class="article-card-footer">' +
            '<div class="article-card-meta">' +
              '<span class="article-category">' + escapeHtml(a.category || '未分类') + '</span>' +
              '<span class="article-author">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="meta-icon">' +
                  '<circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 00-16 0"/>' +
                '</svg>' +
                escapeHtml(a.author || '匿名') +
              '</span>' +
              '<span class="article-reads">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="meta-icon">' +
                  '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>' +
                  '<circle cx="12" cy="12" r="3"/>' +
                '</svg>' +
                formatReadCount(a.read_count) +
              '</span>' +
              '<span class="article-status ' + badgeClass + '">' + escapeHtml(a.status) + '</span>' +
              '<span class="article-date">' + dateStr + '</span>' +
            '</div>' +
            '<div class="article-card-actions">' +
              '<button class="action-btn action-view-article" data-id="' + a.id + '" title="查看详情">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                  '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>' +
                  '<circle cx="12" cy="12" r="3"/>' +
                '</svg>' +
                '<span>查看</span>' +
              '</button>' +
              '<button class="action-btn action-comment" data-id="' + a.id + '" title="留言">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                  '<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>' +
                '</svg>' +
                '<span>留言</span>' +
              '</button>' +
              '<button class="action-btn action-edit-article" data-id="' + a.id + '" title="编辑">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                  '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 113 3L7 19l-4 1 1-4 12.5-12.5z"/>' +
                '</svg>' +
                '<span>编辑</span>' +
              '</button>' +
              '<button class="action-btn action-delete-article" data-id="' + a.id + '" data-title="' + escapeHtml(a.title) + '" title="删除">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                  '<polyline points="3 6 5 6 21 6"/><path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>' +
                '</svg>' +
                '<span>删除</span>' +
              '</button>' +
              '<a class="action-btn" href="' + API_BASE + '/articles/' + a.id + '/download" title="下载" download>' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                  '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>' +
                  '<polyline points="7 10 12 15 17 10"/>' +
                  '<line x1="12" y1="15" x2="12" y2="3"/>' +
                '</svg>' +
                '<span>下载</span>' +
              '</a>' +
            '</div>' +
          '</div>' +
        '</div>';
    });
    container.innerHTML = html;

    container.querySelectorAll('.action-view-article').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        openArticleDetail(this.dataset.id);
      });
    });

    container.querySelectorAll('.action-edit-article').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        openArticleEditor(this.dataset.id);
      });
    });

    container.querySelectorAll('.action-delete-article').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (!confirm('确定删除文章「' + this.dataset.title + '」吗？')) return;
        fetch(API_BASE + '/articles/' + this.dataset.id, { method: 'DELETE' })
          .then(function (res) { if (res.ok) doArticleSearch(); else alert('删除失败'); })
          .catch(function () { alert('删除失败'); });
      });
    });

    // 绑定留言事件
    container.querySelectorAll('.action-comment').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        var aid = this.dataset.id;
        var title = this.closest('.article-card').querySelector('.article-card-title').textContent;
        var msg = prompt('给「' + title + '」留言：');
        if (msg && msg.trim()) {
          fetch(API_BASE + '/articles/' + aid + '/comments', {
            method: 'POST',
            headers: jsonHeaders(),
            body: JSON.stringify({ article_id: parseInt(aid), user_id: currentUserId(), content: msg.trim() }),
          })
            .then(function (res) { return res.json(); })
            .then(function () { alert('留言成功！'); })
            .catch(function () { alert('留言失败'); });
        }
      });
    });

    // 点击文章卡片打开详情并增加阅读量
    container.querySelectorAll('.article-card').forEach(function (card) {
      card.addEventListener('click', function (e) {
        if (e.target.closest('.action-btn')) return;
        openArticleDetail(this.dataset.id);
      });
    });
  }

  function openArticleDetail(aid) {
    Promise.all([
      fetch(API_BASE + '/articles/' + aid).then(function (res) { return res.json(); }),
      fetch(API_BASE + '/articles/' + aid + '/comments').then(function (res) { return res.json(); }),
      fetch(API_BASE + '/articles/' + aid + '/view', { method: 'POST' }).catch(function () { return null; }),
    ])
      .then(function (result) {
        var article = result[0];
        var comments = result[1] || [];
        var commentsHtml = comments.length
          ? comments.map(function (c) {
              return '<div class="comment-item">' +
                '<div class="comment-head"><strong>用户 #' + c.user_id + '</strong>' +
                '<button class="mini-link comment-delete" data-id="' + c.id + '">删除</button></div>' +
                '<p>' + escapeHtml(c.content) + '</p>' +
                '<small>' + (c.created_at ? c.created_at.slice(0, 16).replace('T', ' ') : '') + '</small>' +
              '</div>';
            }).join('')
          : '<p class="detail-muted">暂无留言</p>';
        showInfoModal(
          escapeHtml(article.title),
          '<div class="article-detail">' +
            '<div class="detail-meta">' +
              '<span>' + escapeHtml(article.category || '未分类') + '</span>' +
              '<span>' + escapeHtml(article.author || '匿名') + '</span>' +
              '<span>' + escapeHtml(article.status || '已发布') + '</span>' +
              '<span>' + formatReadCount(article.read_count || 0) + ' 次阅读</span>' +
              '<span>' + (article.created_at ? article.created_at.slice(0, 10) : '') + '</span>' +
            '</div>' +
            (article.cover_image ? '<img class="article-cover" src="' + escapeHtml(article.cover_image) + '" alt="文章封面" />' : '') +
            (article.summary ? '<p class="article-card-summary">' + escapeHtml(article.summary) + '</p>' : '') +
            '<p class="article-detail-content">' + escapeHtml(article.content || article.summary || '') + '</p>' +
            '<div class="detail-divider"></div>' +
            '<h3 class="detail-subtitle">留言</h3>' +
            '<div class="comment-list">' + commentsHtml + '</div>' +
            '<div class="comment-compose">' +
              '<textarea class="form-textarea" id="articleDetailComment" rows="3" placeholder="写下你的留言..."></textarea>' +
              '<button class="btn btn-primary" id="articleDetailSubmit">提交留言</button>' +
            '</div>' +
          '</div>'
        );
        document.getElementById('articleDetailSubmit').addEventListener('click', function () {
          var content = document.getElementById('articleDetailComment').value.trim();
          if (!content) return;
          fetch(API_BASE + '/articles/' + aid + '/comments', {
            method: 'POST',
            headers: jsonHeaders(),
            body: JSON.stringify({ article_id: parseInt(aid), user_id: currentUserId(), content: content }),
          })
            .then(function (res) { if (!res.ok) throw new Error('comment failed'); return res.json(); })
            .then(function () { openArticleDetail(aid); })
            .catch(function () { alert('留言失败'); });
        });
        document.querySelectorAll('.comment-delete').forEach(function (btn) {
          btn.addEventListener('click', function () {
            if (!confirm('确定删除这条留言吗？')) return;
            fetch(API_BASE + '/articles/' + aid + '/comments/' + this.dataset.id, { method: 'DELETE' })
              .then(function (res) { if (res.ok) openArticleDetail(aid); else alert('删除失败'); })
              .catch(function () { alert('删除失败'); });
          });
        });
      })
      .catch(function () { alert('加载文章详情失败'); });
  }

  function formatReadCount(num) {
    if (!num) return '0';
    if (num >= 10000) return (num / 10000).toFixed(1) + 'w';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'k';
    return num.toString();
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function truncate(str, maxLen) {
    if (!str) return '';
    return str.length > maxLen ? str.slice(0, maxLen) + '...' : str;
  }

  /**
   * 咨询记录页 — 搜索栏 + 列表
   */
  function renderRecords() {
    return (
      '<div class="search-bar">' +
        '<div class="search-fields">' +
          '<div class="search-field">' +
            '<label class="search-label">会话ID</label>' +
            '<input type="text" class="search-input" id="rSid" placeholder="输入会话ID精确查找" />' +
          '</div>' +
          '<div class="search-field">' +
            '<label class="search-label">会话标题</label>' +
            '<input type="text" class="search-input" id="rTitle" placeholder="输入标题关键词" />' +
          '</div>' +
          '<div class="search-field"></div>' +
        '</div>' +
        '<div class="search-actions">' +
          '<button class="btn btn-primary" id="btnRecordSearch">查询</button>' +
          '<button class="btn btn-default" id="btnRecordReset">重置</button>' +
          '<button class="btn btn-success" id="btnRecordCreate">+ 新增记录</button>' +
        '</div>' +
      '</div>' +
      // 统计提示
      '<p class="records-count" id="recordsCount"></p>' +
      // 列表
      '<div class="records-table-wrap">' +
        '<table class="records-table">' +
          '<thead><tr>' +
            '<th class="col-pin"></th>' +
            '<th class="col-id">会话ID</th>' +
            '<th class="col-tag">情绪标签</th>' +
            '<th class="col-title">会话标题</th>' +
            '<th class="col-time">时间</th>' +
            '<th class="col-enter">进入</th>' +
            '<th class="col-actions">操作</th>' +
          '</tr></thead>' +
          '<tbody id="recordsTbody">' +
            '<tr><td colspan="7" class="records-loading">加载中...</td></tr>' +
          '</tbody>' +
        '</table>' +
      '</div>'
    );
  }

  function loadRecords() {
    doRecordSearch();
    document.getElementById('btnRecordSearch').addEventListener('click', doRecordSearch);
    document.getElementById('btnRecordReset').addEventListener('click', function () {
      document.getElementById('rSid').value = '';
      document.getElementById('rTitle').value = '';
      doRecordSearch();
    });
    document.getElementById('btnRecordCreate').addEventListener('click', openRecordCreator);
  }

  function openRecordCreator() {
    showInfoModal(
      '新增咨询记录',
      '<div class="form-group">' +
        '<label class="form-label">标题 <span class="required">*</span></label>' +
        '<input type="text" class="form-input" id="newRecordTitle" placeholder="例如：睡眠压力咨询" />' +
      '</div>' +
      '<div class="form-group">' +
        '<label class="form-label">情绪标签</label>' +
        '<input type="text" class="form-input" id="newRecordTag" placeholder="例如：焦虑、低落、平静" />' +
      '</div>' +
      '<div class="form-group">' +
        '<label class="form-label">摘要</label>' +
        '<textarea class="form-textarea" id="newRecordSummary" rows="4" placeholder="记录本次咨询的重点"></textarea>' +
      '</div>' +
      '<div class="form-group">' +
        '<label class="form-label">可见范围</label>' +
        '<select class="form-input" id="newRecordVisibility">' +
          '<option value="公开">公开</option>' +
          '<option value="私人">私人</option>' +
        '</select>' +
      '</div>' +
      '<div class="modal-footer inline-footer">' +
        '<button class="btn btn-default" id="newRecordCancel">取消</button>' +
        '<button class="btn btn-primary" id="newRecordSave">保存</button>' +
      '</div>'
    );
    document.getElementById('newRecordCancel').addEventListener('click', hideInfoModal);
    document.getElementById('newRecordSave').addEventListener('click', function () {
      var title = document.getElementById('newRecordTitle').value.trim();
      if (!title) { alert('请填写标题'); return; }
      fetch(API_BASE + '/consultations/', {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({
          user_id: currentUserId(),
          title: title,
          emotion_tag: document.getElementById('newRecordTag').value.trim(),
          summary: document.getElementById('newRecordSummary').value.trim(),
          visibility: document.getElementById('newRecordVisibility').value,
        }),
      })
        .then(function (res) { if (!res.ok) throw new Error('create failed'); return res.json(); })
        .then(function () { hideInfoModal(); doRecordSearch(); })
        .catch(function () { alert('保存失败'); });
    });
  }

  function doRecordSearch() {
    var sid = encodeURIComponent(document.getElementById('rSid').value.trim());
    var title = encodeURIComponent(document.getElementById('rTitle').value.trim());
    var params = 'sid=' + sid + '&title=' + title;
    fetch(API_BASE + '/consultations/?' + params)
      .then(function (res) { return res.json(); })
      .then(renderRecordsTable)
      .catch(function () {
        document.getElementById('recordsTbody').innerHTML =
          '<tr><td colspan="7" class="records-empty">加载失败，请重试</td></tr>';
      });
  }

  function renderRecordsTable(records) {
    var tbody = document.getElementById('recordsTbody');
    document.getElementById('recordsCount').textContent =
      '共 ' + records.length + ' 条咨询记录';

    if (!records || records.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="records-empty">暂无匹配的咨询记录</td></tr>';
      return;
    }

    var html = '';
    records.forEach(function (r) {
      var dateStr = r.created_at ? r.created_at.slice(0, 16).replace('T', ' ') : '';
      html +=
        '<tr class="' + (r.pinned ? 'row-pinned' : '') + '">' +
          '<td class="col-pin">' + (r.pinned ? '<span class="pin-badge" title="已置顶">📌</span>' : '') + '</td>' +
          '<td class="col-id">#' + r.id + '</td>' +
          '<td class="col-tag">' +
            '<span class="emotion-tag">' + escapeHtml(r.emotion_tag || '未标记') + '</span>' +
          '</td>' +
          '<td class="col-title">' + escapeHtml(r.title) + '</td>' +
          '<td class="col-time">' + dateStr + '</td>' +
          '<td class="col-enter">' +
            '<button class="action-btn action-enter" data-id="' + r.id + '" data-cid="' + (r.conversation_id || '') + '">进入</button>' +
          '</td>' +
          '<td class="col-actions">' +
            '<button class="action-btn action-edit" data-id="' + r.id + '" data-title="' + escapeHtml(r.title) + '">编辑标题</button>' +
            '<button class="action-btn action-pin" data-id="' + r.id + '" data-pinned="' + r.pinned + '">' +
              (r.pinned ? '取消置顶' : '置顶') +
            '</button>' +
            '<button class="action-btn action-delete" data-id="' + r.id + '" data-title="' + escapeHtml(r.title) + '">删除</button>' +
          '</td>' +
        '</tr>';
    });
    tbody.innerHTML = html;

    // 绑定事件
    tbody.querySelectorAll('.action-enter').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var cid = this.dataset.cid;
        if (cid) {
          localStorage.setItem('mh_conv_id', cid);
          navigateToPage('consult');
        } else {
          openManualConsultation(this.dataset.id);
        }
      });
    });
    tbody.querySelectorAll('.action-edit').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var newTitle = prompt('编辑标题：', this.dataset.title);
        if (newTitle && newTitle.trim() && newTitle.trim() !== this.dataset.title) {
          fetch(API_BASE + '/consultations/' + this.dataset.id, {
            method: 'PATCH',
            headers: jsonHeaders(),
            body: JSON.stringify({ title: newTitle.trim() }),
          })
            .then(function (res) { if (res.ok) doRecordSearch(); else alert('编辑失败'); })
            .catch(function () { alert('编辑失败'); });
        }
      });
    });
    tbody.querySelectorAll('.action-pin').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var isPinned = this.dataset.pinned === 'true';
        fetch(API_BASE + '/consultations/' + this.dataset.id, {
          method: 'PATCH',
          headers: jsonHeaders(),
          body: JSON.stringify({ pinned: !isPinned }),
        })
          .then(function (res) { if (res.ok) doRecordSearch(); else alert('操作失败'); })
          .catch(function () { alert('操作失败'); });
      });
    });
    tbody.querySelectorAll('.action-delete').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (confirm('确定要删除会话 #' + this.dataset.id + '「' + this.dataset.title + '」吗？此操作不可撤销。')) {
          fetch(API_BASE + '/consultations/' + this.dataset.id, { method: 'DELETE' })
            .then(function (res) { if (res.ok) doRecordSearch(); else alert('删除失败'); })
            .catch(function () { alert('删除失败'); });
        }
      });
    });
  }

  function openManualConsultation(id) {
    fetch(API_BASE + '/consultations/' + id)
      .then(function (res) { return res.json(); })
      .then(function (r) {
        showInfoModal(
          '咨询记录 #' + r.id,
          '<div class="detail-grid">' +
            '<span>标题</span><strong>' + escapeHtml(r.title || '未命名') + '</strong>' +
            '<span>情绪标签</span><strong>' + escapeHtml(r.emotion_tag || '未标记') + '</strong>' +
            '<span>可见范围</span><strong>' + escapeHtml(r.visibility || '公开') + '</strong>' +
            '<span>时间</span><strong>' + (r.created_at ? r.created_at.slice(0, 16).replace('T', ' ') : '') + '</strong>' +
          '</div>' +
          '<div class="detail-divider"></div>' +
          '<p class="article-detail-content">' + escapeHtml(r.summary || '这条记录没有关联 AI 对话内容，可在标题编辑、置顶和删除中管理。') + '</p>'
        );
      })
      .catch(function () { alert('加载记录失败'); });
  }

  /**
   * 情绪日志页 — 发布表单 + 搜索 + 结果列表
   */
  function renderMood() {
    return (
      // 发布表单
      '<div class="search-bar">' +
        '<p class="section-label">发布情绪日志</p>' +
        '<div class="search-fields">' +
          '<div class="search-field">' +
            '<label class="search-label">情绪评分 <span class="required">*</span></label>' +
            '<select class="search-input" id="mScore">' +
              '<option value="">请选择评分</option>' +
              Array.from({length: 10}, function (_, i) { return '<option value="' + (i+1) + '">' + (i+1) + ' 分 ' + scoreEmoji(i+1) + '</option>'; }).join('') +
            '</select>' +
          '</div>' +
          '<div class="search-field">' +
            '<label class="search-label">情绪触发因素</label>' +
            '<input type="text" class="search-input" id="mTrigger" placeholder="什么触发了你的情绪？" />' +
          '</div>' +
          '<div class="search-field">' +
            '<label class="search-label">可见范围 <span class="required">*</span></label>' +
            '<select class="search-input" id="mVisibility">' +
              '<option value="公开">公开（可被他人查看）</option>' +
              '<option value="私人">私人（仅自己可见）</option>' +
            '</select>' +
          '</div>' +
        '</div>' +
        '<div class="search-field" style="margin-bottom:16px;">' +
          '<label class="search-label">日记内容 <span class="required">*</span></label>' +
          '<textarea class="form-textarea" id="mNote" rows="3" placeholder="记录你此刻的感受和想法..."></textarea>' +
        '</div>' +
        '<div class="search-actions">' +
          '<button class="btn btn-primary" id="btnPublishMood">发布日志</button>' +
        '</div>' +
      '</div>' +
      // 搜索栏
      '<div class="search-bar">' +
        '<p class="section-label">探索公开日志</p>' +
        '<div class="search-fields">' +
          '<div class="search-field">' +
            '<label class="search-label">用户ID</label>' +
            '<input type="text" class="search-input" id="mSearchUid" placeholder="输入用户ID" />' +
          '</div>' +
          '<div class="search-field">' +
            '<label class="search-label">情绪评分</label>' +
            '<select class="search-input" id="mSearchScore">' +
              '<option value="">不限</option>' +
              Array.from({length: 10}, function (_, i) { return '<option value="' + (i+1) + '">' + (i+1) + ' 分</option>'; }).join('') +
            '</select>' +
          '</div>' +
          '<div class="search-field"></div>' +
        '</div>' +
        '<div class="search-actions">' +
          '<button class="btn btn-primary" id="btnMoodSearch">查询</button>' +
          '<button class="btn btn-default" id="btnMoodReset">重置</button>' +
        '</div>' +
      '</div>' +
      '<p class="records-count" id="moodCount"></p>' +
      '<div class="mood-list" id="moodList">' +
        '<p class="article-list-hint">加载中...</p>' +
      '</div>'
    );
  }

  function scoreEmoji(score) {
    if (score >= 9) return '😄';
    if (score >= 7) return '🙂';
    if (score >= 5) return '😐';
    if (score >= 3) return '😟';
    return '😢';
  }

  function loadMood() {
    doMoodSearch();

    document.getElementById('btnPublishMood').addEventListener('click', publishMood);
    document.getElementById('btnMoodSearch').addEventListener('click', doMoodSearch);
    document.getElementById('btnMoodReset').addEventListener('click', function () {
      document.getElementById('mSearchUid').value = '';
      document.getElementById('mSearchScore').value = '';
      doMoodSearch();
    });
  }

  function publishMood() {
    var score = document.getElementById('mScore').value;
    var trigger = document.getElementById('mTrigger').value.trim();
    var visibility = document.getElementById('mVisibility').value;
    var note = document.getElementById('mNote').value.trim();

    if (!score) { alert('请选择情绪评分'); return; }
    if (!note) { alert('请填写日记内容'); return; }

    fetch(API_BASE + '/mood/', {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({
        user_id: currentUserId(),
        score: parseFloat(score),
        trigger: trigger,
        note: note,
        visibility: visibility,
      }),
    })
      .then(function (res) {
        if (!res.ok) throw new Error('发布失败');
        return res.json();
      })
      .then(function () {
        document.getElementById('mScore').value = '';
        document.getElementById('mTrigger').value = '';
        document.getElementById('mNote').value = '';
        doMoodSearch();
      })
      .catch(function () { alert('发布失败，请重试'); });
  }

  function doMoodSearch() {
    var uid = encodeURIComponent(document.getElementById('mSearchUid').value.trim());
    var score = encodeURIComponent(document.getElementById('mSearchScore').value);
    var params = 'user_id=' + uid + '&score=' + score;
    fetch(API_BASE + '/mood/?' + params)
      .then(function (res) { return res.json(); })
      .then(renderMoodList)
      .catch(function () {
        document.getElementById('moodList').innerHTML =
          '<p class="article-list-empty">加载失败，请重试</p>';
      });
  }

  function renderMoodList(list) {
    var container = document.getElementById('moodList');
    document.getElementById('moodCount').textContent =
      '共 ' + (list ? list.length : 0) + ' 条公开日志';

    if (!list || list.length === 0) {
      container.innerHTML = '<p class="article-list-empty">暂无公开的情绪日志</p>';
      return;
    }

    var html = '';
    list.forEach(function (m) {
      var dateStr = m.created_at ? m.created_at.slice(0, 16).replace('T', ' ') : '';
      html +=
        '<div class="mood-card">' +
          '<div class="mood-card-top">' +
            '<div class="mood-score-badge" style="background:' + scoreColor(m.score) + '">' +
              scoreEmoji(m.score) + ' ' + m.score + ' 分' +
            '</div>' +
            '<span class="mood-user">用户 #' + m.user_id + '</span>' +
            '<span class="mood-trigger">触发: ' + escapeHtml(m.trigger || '未记录') + '</span>' +
            '<span class="mood-date">' + dateStr + '</span>' +
          '</div>' +
          '<div class="mood-card-body">' +
            '<p>' + escapeHtml(m.note) + '</p>' +
          '</div>' +
          '<div class="mood-card-actions">' +
            '<button class="action-btn action-detail" data-id="' + m.id + '" ' +
              'data-score="' + m.score + '" ' +
              'data-trigger="' + escapeHtml(m.trigger || '') + '" ' +
              'data-note="' + escapeHtml(m.note) + '" ' +
              'data-user="' + m.user_id + '" ' +
              'data-time="' + dateStr + '">查看</button>' +
            '<button class="action-btn action-bookmark" data-id="' + m.id + '">' +
              '⭐ ' + m.bookmark_count +
            '</button>' +
          '</div>' +
        '</div>';
    });
    container.innerHTML = html;

    // 详情按钮
    container.querySelectorAll('.action-detail').forEach(function (btn) {
      btn.addEventListener('click', function () {
        showInfoModal(
          '情绪日志详情',
          '<div class="detail-grid">' +
            '<span>用户ID</span><strong>#' + this.dataset.user + '</strong>' +
            '<span>情绪评分</span><strong>' + this.dataset.score + ' / 10</strong>' +
            '<span>触发因素</span><strong>' + escapeHtml(this.dataset.trigger || '未记录') + '</strong>' +
            '<span>时间</span><strong>' + escapeHtml(this.dataset.time || '') + '</strong>' +
          '</div>' +
          '<div class="detail-divider"></div>' +
          '<p class="article-detail-content">' + escapeHtml(this.dataset.note || '') + '</p>'
        );
      });
    });

    // 收藏按钮
    container.querySelectorAll('.action-bookmark').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var mid = this.dataset.id;
        fetch(API_BASE + '/mood/' + mid + '/bookmark?user_id=' + currentUserId(), { method: 'POST' })
          .then(function (res) { return res.json(); })
          .then(function (data) {
            btn.innerHTML = '⭐ ' + data.bookmark_count;
          })
          .catch(function () {});
      });
    });
  }

  function scoreColor(score) {
    if (score >= 8) return '#ECFDF5;color:#059669';
    if (score >= 6) return '#EFF6FF;color:#2563EB';
    if (score >= 4) return '#FEF3C7;color:#D97706';
    return '#FEF2F2;color:#DC2626';
  }

  /**
   * 社区讨论页 — 发帖 + 查询 + 详情回复
   */
  function renderCommunity() {
    return (
      '<div class="search-bar">' +
        '<p class="section-label">发布讨论</p>' +
        '<div class="search-fields">' +
          '<div class="search-field">' +
            '<label class="search-label">标题 <span class="required">*</span></label>' +
            '<input type="text" class="search-input" id="dTitle" placeholder="给讨论起个标题" />' +
          '</div>' +
          '<div class="search-field">' +
            '<label class="search-label">分类</label>' +
            '<input type="text" class="search-input" id="dCategory" placeholder="例如：压力、睡眠、人际关系" />' +
          '</div>' +
          '<div class="search-field"></div>' +
        '</div>' +
        '<div class="search-field" style="margin-bottom:16px;">' +
          '<label class="search-label">内容</label>' +
          '<textarea class="form-textarea" id="dContent" rows="4" placeholder="写下你想讨论的问题或经验..."></textarea>' +
        '</div>' +
        '<div class="search-actions">' +
          '<button class="btn btn-primary" id="btnCreateDiscussion">发布讨论</button>' +
        '</div>' +
      '</div>' +
      '<div class="search-bar">' +
        '<p class="section-label">社区讨论</p>' +
        '<div class="search-fields">' +
          '<div class="search-field">' +
            '<label class="search-label">标题关键词</label>' +
            '<input type="text" class="search-input" id="dSearchTitle" placeholder="搜索标题" />' +
          '</div>' +
          '<div class="search-field">' +
            '<label class="search-label">分类</label>' +
            '<input type="text" class="search-input" id="dSearchCategory" placeholder="搜索分类" />' +
          '</div>' +
          '<div class="search-field"></div>' +
        '</div>' +
        '<div class="search-actions">' +
          '<button class="btn btn-primary" id="btnDiscussionSearch">查询</button>' +
          '<button class="btn btn-default" id="btnDiscussionReset">重置</button>' +
        '</div>' +
      '</div>' +
      '<p class="records-count" id="discussionCount"></p>' +
      '<div class="discussion-list" id="discussionList">' +
        '<p class="article-list-hint">加载中...</p>' +
      '</div>'
    );
  }

  function loadCommunity() {
    doDiscussionSearch();
    document.getElementById('btnCreateDiscussion').addEventListener('click', createDiscussion);
    document.getElementById('btnDiscussionSearch').addEventListener('click', doDiscussionSearch);
    document.getElementById('btnDiscussionReset').addEventListener('click', function () {
      document.getElementById('dSearchTitle').value = '';
      document.getElementById('dSearchCategory').value = '';
      doDiscussionSearch();
    });
  }

  function createDiscussion() {
    var title = document.getElementById('dTitle').value.trim();
    var category = document.getElementById('dCategory').value.trim();
    var body = document.getElementById('dContent').value.trim();
    if (!title) { alert('请填写讨论标题'); return; }

    fetch(API_BASE + '/discussions/', {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({
        title: title,
        category: category,
        content: body,
        user_id: currentUserId(),
      }),
    })
      .then(function (res) { if (!res.ok) throw new Error('create failed'); return res.json(); })
      .then(function () {
        document.getElementById('dTitle').value = '';
        document.getElementById('dCategory').value = '';
        document.getElementById('dContent').value = '';
        doDiscussionSearch();
      })
      .catch(function () { alert('发布失败，请重试'); });
  }

  function doDiscussionSearch() {
    var title = encodeURIComponent(document.getElementById('dSearchTitle').value.trim());
    var category = encodeURIComponent(document.getElementById('dSearchCategory').value.trim());
    fetch(API_BASE + '/discussions/?title=' + title + '&category=' + category)
      .then(function (res) { return res.json(); })
      .then(renderDiscussionList)
      .catch(function () {
        document.getElementById('discussionList').innerHTML =
          '<p class="article-list-empty">加载失败，请重试</p>';
      });
  }

  function renderDiscussionList(list) {
    var container = document.getElementById('discussionList');
    document.getElementById('discussionCount').textContent =
      '共 ' + (list ? list.length : 0) + ' 条讨论';
    if (!list || list.length === 0) {
      container.innerHTML = '<p class="article-list-empty">暂无讨论</p>';
      return;
    }

    container.innerHTML = list.map(function (d) {
      var dateStr = d.created_at ? d.created_at.slice(0, 16).replace('T', ' ') : '';
      return '<div class="discussion-card" data-id="' + d.id + '">' +
        '<div class="discussion-main">' +
          '<div class="discussion-title-row">' +
            '<h3 class="article-card-title">' + escapeHtml(d.title) + '</h3>' +
            '<span class="article-category">' + escapeHtml(d.category || '未分类') + '</span>' +
          '</div>' +
          '<p class="article-card-summary">' + escapeHtml(truncate(d.content || '暂无正文', 150)) + '</p>' +
          '<div class="discussion-meta">' +
            '<span>用户 #' + d.user_id + '</span>' +
            '<span>' + d.reply_count + ' 条回复</span>' +
            '<span>' + d.view_count + ' 次浏览</span>' +
            '<span>' + dateStr + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="article-card-actions">' +
          '<button class="action-btn action-discussion-view" data-id="' + d.id + '">查看</button>' +
          '<button class="action-btn action-discussion-edit" data-id="' + d.id + '" data-title="' + escapeHtml(d.title) + '" data-category="' + escapeHtml(d.category || '') + '" data-content="' + escapeHtml(d.content || '') + '">编辑</button>' +
          '<button class="action-btn action-discussion-delete" data-id="' + d.id + '" data-title="' + escapeHtml(d.title) + '">删除</button>' +
        '</div>' +
      '</div>';
    }).join('');

    container.querySelectorAll('.discussion-card').forEach(function (card) {
      card.addEventListener('click', function (e) {
        if (e.target.closest('.action-btn')) return;
        openDiscussionDetail(this.dataset.id);
      });
    });
    container.querySelectorAll('.action-discussion-view').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        openDiscussionDetail(this.dataset.id);
      });
    });
    container.querySelectorAll('.action-discussion-edit').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        openDiscussionEditor(this.dataset);
      });
    });
    container.querySelectorAll('.action-discussion-delete').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (!confirm('确定删除讨论「' + this.dataset.title + '」吗？')) return;
        fetch(API_BASE + '/discussions/' + this.dataset.id, { method: 'DELETE' })
          .then(function (res) { if (res.ok) doDiscussionSearch(); else alert('删除失败'); })
          .catch(function () { alert('删除失败'); });
      });
    });
  }

  function openDiscussionEditor(data) {
    showInfoModal(
      '编辑讨论',
      '<div class="form-group">' +
        '<label class="form-label">标题</label>' +
        '<input type="text" class="form-input" id="editDiscussionTitle" value="' + escapeHtml(data.title || '') + '" />' +
      '</div>' +
      '<div class="form-group">' +
        '<label class="form-label">分类</label>' +
        '<input type="text" class="form-input" id="editDiscussionCategory" value="' + escapeHtml(data.category || '') + '" />' +
      '</div>' +
      '<div class="form-group">' +
        '<label class="form-label">内容</label>' +
        '<textarea class="form-textarea" id="editDiscussionContent" rows="5">' + escapeHtml(data.content || '') + '</textarea>' +
      '</div>' +
      '<div class="modal-footer inline-footer">' +
        '<button class="btn btn-default" id="editDiscussionCancel">取消</button>' +
        '<button class="btn btn-primary" id="editDiscussionSave">保存</button>' +
      '</div>'
    );
    document.getElementById('editDiscussionCancel').addEventListener('click', hideInfoModal);
    document.getElementById('editDiscussionSave').addEventListener('click', function () {
      var title = document.getElementById('editDiscussionTitle').value.trim();
      if (!title) { alert('请填写讨论标题'); return; }
      fetch(API_BASE + '/discussions/' + data.id, {
        method: 'PATCH',
        headers: jsonHeaders(),
        body: JSON.stringify({
          title: title,
          category: document.getElementById('editDiscussionCategory').value.trim(),
          content: document.getElementById('editDiscussionContent').value.trim(),
          user_id: currentUserId(),
        }),
      })
        .then(function (res) { if (!res.ok) throw new Error('update failed'); return res.json(); })
        .then(function () { hideInfoModal(); doDiscussionSearch(); })
        .catch(function () { alert('保存失败'); });
    });
  }

  function openDiscussionDetail(id) {
    Promise.all([
      fetch(API_BASE + '/discussions/' + id + '/view', { method: 'POST' }).catch(function () { return null; }),
      fetch(API_BASE + '/discussions/' + id).then(function (res) { return res.json(); }),
      fetch(API_BASE + '/discussions/' + id + '/replies').then(function (res) { return res.json(); }),
    ])
      .then(function (result) {
        var d = result[1];
        var replies = result[2] || [];
        var repliesHtml = replies.length
          ? replies.map(function (r) {
              return '<div class="comment-item">' +
                '<div class="comment-head"><strong>用户 #' + r.user_id + '</strong>' +
                '<button class="mini-link reply-delete" data-id="' + r.id + '">删除</button></div>' +
                '<p>' + escapeHtml(r.content) + '</p>' +
                '<small>' + (r.created_at ? r.created_at.slice(0, 16).replace('T', ' ') : '') + '</small>' +
              '</div>';
            }).join('')
          : '<p class="detail-muted">还没有回复</p>';
        showInfoModal(
          escapeHtml(d.title),
          '<div class="article-detail">' +
            '<div class="detail-meta">' +
              '<span>' + escapeHtml(d.category || '未分类') + '</span>' +
              '<span>用户 #' + d.user_id + '</span>' +
              '<span>' + d.reply_count + ' 条回复</span>' +
            '</div>' +
            '<p class="article-detail-content">' + escapeHtml(d.content || '暂无正文') + '</p>' +
            '<div class="detail-divider"></div>' +
            '<h3 class="detail-subtitle">回复</h3>' +
            '<div class="comment-list">' + repliesHtml + '</div>' +
            '<div class="comment-compose">' +
              '<textarea class="form-textarea" id="discussionReplyContent" rows="3" placeholder="写下你的回复..."></textarea>' +
              '<button class="btn btn-primary" id="discussionReplySubmit">回复</button>' +
            '</div>' +
          '</div>'
        );
        document.getElementById('discussionReplySubmit').addEventListener('click', function () {
          var content = document.getElementById('discussionReplyContent').value.trim();
          if (!content) return;
          fetch(API_BASE + '/discussions/' + id + '/replies', {
            method: 'POST',
            headers: jsonHeaders(),
            body: JSON.stringify({ discussion_id: parseInt(id), content: content, user_id: currentUserId() }),
          })
            .then(function (res) { if (!res.ok) throw new Error('reply failed'); return res.json(); })
            .then(function () { openDiscussionDetail(id); doDiscussionSearch(); })
            .catch(function () { alert('回复失败'); });
        });
        document.querySelectorAll('.reply-delete').forEach(function (btn) {
          btn.addEventListener('click', function () {
            if (!confirm('确定删除这条回复吗？')) return;
            fetch(API_BASE + '/discussions/' + id + '/replies/' + this.dataset.id, { method: 'DELETE' })
              .then(function (res) { if (res.ok) { openDiscussionDetail(id); doDiscussionSearch(); } else alert('删除失败'); })
              .catch(function () { alert('删除失败'); });
          });
        });
      })
      .catch(function () { alert('加载讨论详情失败'); });
  }

  /**
   * 咨询入口 — AI 聊天（DB 持久化 + 全量上下文记忆）
   */
  var currentConvId = null;
  var currentVisibility = "公开";

  function renderConsult() {
    return (
      '<div class="consult-layout">' +
        // 左侧历史栏
        '<div class="consult-sidebar">' +
          '<div class="consult-sidebar-header">' +
            '<span>咨询历史</span>' +
          '</div>' +
          '<div class="consult-new-chat">' +
            '<button class="btn btn-primary btn-sm" id="btnNewChat">+ 新对话</button>' +
          '</div>' +
          '<div class="consult-history-list" id="consultHistoryList">' +
            '<p class="history-loading">加载中...</p>' +
          '</div>' +
        '</div>' +
        // 右侧聊天区
        '<div class="chat-container">' +
          '<div class="chat-messages" id="chatMessages">' +
            '<div class="chat-msg chat-msg-ai">' +
              '<div class="chat-bubble">你好！我是你的AI心理助手 🌸<br>我有一百万上下文记忆，会记得你说过的每一句话。<br>有什么想聊的吗？</div>' +
            '</div>' +
          '</div>' +
          '<div class="chat-input-bar">' +
            '<input type="text" class="chat-input" id="chatInput" placeholder="输入你想说的话..." />' +
            '<button class="btn btn-primary" id="btnChatSend">发送</button>' +
          '</div>' +
        '</div>' +
      '</div>' +
      // 选择公开/私人弹窗
      '<div class="modal-overlay" id="visibilityModal" style="display:none;">' +
        '<div class="modal modal-sm">' +
          '<div class="modal-header">' +
            '<h2 class="modal-title">选择对话可见范围</h2>' +
          '</div>' +
          '<div class="modal-body">' +
            '<p style="font-size:14px;color:var(--color-text-secondary);margin-bottom:16px;">新对话开始前，请选择：</p>' +
            '<div class="visibility-options">' +
              '<button class="vis-option vis-public" id="visPublic">' +
                '<span class="vis-icon">🌐</span>' +
                '<span class="vis-label">公开</span>' +
                '<span class="vis-desc">出现在咨询记录中，他人可查阅</span>' +
              '</button>' +
              '<button class="vis-option vis-private" id="visPrivate">' +
                '<span class="vis-icon">🔒</span>' +
                '<span class="vis-label">私人</span>' +
                '<span class="vis-desc">仅自己可见，不会公开</span>' +
              '</button>' +
            '</div>' +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  function initConsult() {
    // 获取或创建 conversation_id
    currentConvId = localStorage.getItem('mh_conv_id');
    if (!currentConvId) {
      currentConvId = 'conv-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
      localStorage.setItem('mh_conv_id', currentConvId);
    }
    currentVisibility = "公开"; // 默认，实际每次新对话时弹窗选择

    loadChatHistory();
    loadConversationList();

    var input = document.getElementById('chatInput');
    var btn = document.getElementById('btnChatSend');

    function send() {
      var msg = input.value.trim();
      if (!msg) return;
      input.value = '';
      input.disabled = true;
      btn.disabled = true;

      appendMessage('user', msg);
      var loadingId = appendMessage('ai', '思考中...');

      fetch(API_BASE + '/consult/chat', {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify({
          conversation_id: currentConvId,
          message: msg,
          visibility: currentVisibility,
          user_id: currentUserId(),
        }),
      })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          updateMessage(loadingId, data.reply);
          loadConversationList();  // 刷新历史列表
        })
        .catch(function () {
          updateMessage(loadingId, '抱歉，发送失败，请重试。');
        })
        .finally(function () {
          input.disabled = false;
          btn.disabled = false;
          input.focus();
        });
    }

    btn.addEventListener('click', send);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    });

    // 新对话 → 先弹窗选公开/私人
    document.getElementById('btnNewChat').addEventListener('click', function () {
      document.getElementById('visibilityModal').style.display = 'flex';
    });

    document.getElementById('visPublic').addEventListener('click', function () {
      startNewChat('公开');
    });
    document.getElementById('visPrivate').addEventListener('click', function () {
      startNewChat('私人');
    });

    function startNewChat(visibility) {
      document.getElementById('visibilityModal').style.display = 'none';
      currentVisibility = visibility;
      currentConvId = 'conv-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
      localStorage.setItem('mh_conv_id', currentConvId);
      var container = document.getElementById('chatMessages');
      var hint = visibility === '私人' ? '（🔒 私密对话，仅自己可见）' : '（🌐 公开对话，会出现在咨询记录中）';
      container.innerHTML =
        '<div class="chat-msg chat-msg-ai">' +
          '<div class="chat-bubble">新对话开始啦！' + hint + '<br>有什么想聊的？ 🌸</div>' +
        '</div>';
      loadConversationList();
    }

    function appendMessage(role, text) {
      var container = document.getElementById('chatMessages');
      var div = document.createElement('div');
      div.className = 'chat-msg chat-msg-' + (role === 'user' ? 'user' : 'ai');
      var id = 'msg-' + Date.now();
      div.id = id;
      div.innerHTML = '<div class="chat-bubble">' + escapeHtml(text) + '</div>';
      container.appendChild(div);
      container.scrollTop = container.scrollHeight;
      return id;
    }

    function updateMessage(id, text) {
      var div = document.getElementById(id);
      if (div) {
        div.querySelector('.chat-bubble').textContent = text;
        var container = document.getElementById('chatMessages');
        container.scrollTop = container.scrollHeight;
      }
    }
  }

  function loadChatHistory() {
    if (!currentConvId) return;
    fetch(API_BASE + '/consult/history/' + currentConvId)
      .then(function (res) { return res.json(); })
      .then(function (rows) {
        if (!rows || rows.length === 0) return;
        var container = document.getElementById('chatMessages');
        container.innerHTML = '';
        rows.forEach(function (r) {
          var div = document.createElement('div');
          div.className = 'chat-msg chat-msg-' + (r.role === 'user' ? 'user' : 'ai');
          div.innerHTML = '<div class="chat-bubble">' + escapeHtml(r.content) + '</div>';
          container.appendChild(div);
        });
        container.scrollTop = container.scrollHeight;
      })
      .catch(function () {});
  }

  function loadConversationList() {
    fetch(API_BASE + '/consult/conversations')
      .then(function (res) { return res.json(); })
      .then(function (list) {
        var container = document.getElementById('consultHistoryList');
        if (!list || list.length === 0) {
          container.innerHTML = '<p class="history-empty">暂无咨询记录</p>';
          return;
        }
        var html = '';
        list.forEach(function (c) {
          var activeClass = c.conversation_id === currentConvId ? ' active' : '';
          var dateStr = c.started_at ? c.started_at.slice(0, 10) : '';
          var isPublic = c.visibility === '公开';
          html +=
            '<div class="history-item' + activeClass + '" data-cid="' + c.conversation_id + '">' +
              '<div class="history-item-top">' +
                '<p class="history-item-title">' + escapeHtml(c.title) + '</p>' +
                '<button class="vis-toggle ' + (isPublic ? 'vis-toggle-public' : 'vis-toggle-private') + '" ' +
                  'data-cid="' + c.conversation_id + '" data-vis="' + c.visibility + '" title="切换可见性">' +
                  (isPublic ? '🌐' : '🔒') +
                '</button>' +
                '<button class="vis-toggle history-delete" data-cid="' + c.conversation_id + '" title="删除对话">×</button>' +
              '</div>' +
              '<p class="history-item-meta">' + c.message_count + ' 条消息 · ' + dateStr + '</p>' +
            '</div>';
        });
        container.innerHTML = html;

        // 切换可见性按钮
        container.querySelectorAll('.vis-toggle').forEach(function (btn) {
          btn.addEventListener('click', function (e) {
            e.stopPropagation(); // 不触发切换对话
            if (this.classList.contains('history-delete')) return;
            var cid = this.dataset.cid;
            var newVis = this.dataset.vis === '公开' ? '私人' : '公开';
            fetch(API_BASE + '/consult/conversations/' + cid + '/visibility?visibility=' + encodeURIComponent(newVis), {
              method: 'PATCH',
            })
              .then(function (res) { return res.json(); })
              .then(function () { loadConversationList(); })
              .catch(function () {});
          });
        });

        container.querySelectorAll('.history-delete').forEach(function (btn) {
          btn.addEventListener('click', function (e) {
            e.stopPropagation();
            var cid = this.dataset.cid;
            if (!confirm('确定删除这段 AI 对话吗？')) return;
            fetch(API_BASE + '/consult/conversations/' + encodeURIComponent(cid), { method: 'DELETE' })
              .then(function (res) {
                if (!res.ok) throw new Error('delete failed');
                if (currentConvId === cid) {
                  localStorage.removeItem('mh_conv_id');
                  currentConvId = 'conv-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
                  localStorage.setItem('mh_conv_id', currentConvId);
                  document.getElementById('chatMessages').innerHTML =
                    '<div class="chat-msg chat-msg-ai"><div class="chat-bubble">这段对话已删除。可以直接开始新的聊天。</div></div>';
                }
                loadConversationList();
              })
              .catch(function () { alert('删除失败'); });
          });
        });

        // 点击切换对话
        container.querySelectorAll('.history-item').forEach(function (item) {
          item.addEventListener('click', function () {
            currentConvId = this.dataset.cid;
            localStorage.setItem('mh_conv_id', currentConvId);
            loadChatHistory();
            loadConversationList();
          });
        });
      })
      .catch(function () {
        document.getElementById('consultHistoryList').innerHTML =
          '<p class="history-empty">加载失败</p>';
      });
  }

  /**
   * 通用占位页
   */
  function renderPlaceholder(config) {
    return (
      '<div class="content-placeholder">' +
        '<div class="placeholder-icon">' + (config.icon || '📄') + '</div>' +
        '<p class="placeholder-title">' + config.title + '</p>' +
        '<p class="placeholder-desc">此页面内容正在建设中，敬请期待...</p>' +
      '</div>'
    );
  }

  /**
   * 数据分析页 — 顶部四个统计卡片 + 两张图表
   */
  function renderAnalytics() {
    return (
      // 统计卡片
      '<div class="stats-grid" id="statsGrid">' +
        '<div class="stat-card">' +
          '<div class="stat-icon" style="background:#F3EEFF;color:#7C3AED;">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
              '<circle cx="9" cy="7" r="4"/><path d="M3 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>' +
              '<circle cx="17" cy="11" r="2"/><path d="M23 21v-1a3 3 0 00-3-3h-1"/>' +
            '</svg>' +
          '</div>' +
          '<div class="stat-info">' +
            '<span class="stat-label">用户总数</span>' +
            '<span class="stat-value" id="statUsers">--</span>' +
          '</div>' +
        '</div>' +
        '<div class="stat-card">' +
          '<div class="stat-icon" style="background:#FDF2F8;color:#DB2777;">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
              '<path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/>' +
            '</svg>' +
          '</div>' +
          '<div class="stat-info">' +
            '<span class="stat-label">情绪日志</span>' +
            '<span class="stat-value" id="statMoodLogs">--</span>' +
          '</div>' +
        '</div>' +
        '<div class="stat-card">' +
          '<div class="stat-icon" style="background:#EFF6FF;color:#2563EB;">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
              '<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>' +
            '</svg>' +
          '</div>' +
          '<div class="stat-info">' +
            '<span class="stat-label">咨询会话</span>' +
            '<span class="stat-value" id="statConsultations">--</span>' +
          '</div>' +
        '</div>' +
        '<div class="stat-card">' +
          '<div class="stat-icon" style="background:#ECFDF5;color:#059669;">' +
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
              '<circle cx="12" cy="12" r="10"/>' +
              '<path d="M8 14s1.5 3 4 3 4-3 4-3"/>' +
              '<line x1="9" y1="9" x2="9.01" y2="9"/>' +
              '<line x1="15" y1="9" x2="15.01" y2="9"/>' +
            '</svg>' +
          '</div>' +
          '<div class="stat-info">' +
            '<span class="stat-label">平均情绪</span>' +
            '<span class="stat-value" id="statAvgMood">--<span class="stat-unit"> / 10</span></span>' +
          '</div>' +
        '</div>' +
      '</div>' +
      // 图表区 — 左右并排
      '<div class="charts-row">' +
        // 左：情绪趋势折线图
        '<div class="chart-panel">' +
          '<p class="chart-panel-title">情绪趋势分析</p>' +
          '<div class="chart-wrapper"><canvas id="chartMoodTrend"></canvas></div>' +
        '</div>' +
        // 右：咨询会话柱状图
        '<div class="chart-panel">' +
          '<p class="chart-panel-title">咨询会话统计</p>' +
          '<div class="chart-wrapper"><canvas id="chartConsultation"></canvas></div>' +
        '</div>' +
      '</div>' +
      // 底部全宽：用户活跃度趋势
      '<div class="chart-panel chart-panel--full">' +
        '<p class="chart-panel-title">用户活跃度趋势</p>' +
        '<div class="chart-wrapper chart-wrapper--tall"><canvas id="chartUserActivity"></canvas></div>' +
      '</div>'
    );
  }

  // ====== 数据加载 & 图表绘制 ======

  function loadAnalyticsData() {
    destroyCharts();

    // 1. 四卡片数据
    fetch(API_BASE + '/analytics/overview')
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var usersEl = document.getElementById('statUsers');
        var moodEl = document.getElementById('statMoodLogs');
        var consEl = document.getElementById('statConsultations');
        var avgEl = document.getElementById('statAvgMood');
        if (usersEl) usersEl.textContent = formatNumber(data.total_users);
        if (moodEl) moodEl.textContent = formatNumber(data.total_mood_logs);
        if (consEl) consEl.textContent = formatNumber(data.total_consultations);
        if (avgEl) avgEl.innerHTML = data.avg_mood_score + '<span class="stat-unit"> / 10</span>';
      })
      .catch(function () {
        var defaults = ['0', '0', '0', '0<span class="stat-unit"> / 10</span>'];
        ['statUsers', 'statMoodLogs', 'statConsultations', 'statAvgMood'].forEach(function (id, i) {
          var el = document.getElementById(id);
          if (el) el.innerHTML = defaults[i];
        });
      });

    // 2. 情绪趋势图
    fetch(API_BASE + '/analytics/mood-trend?days=14')
      .then(function (res) { return res.json(); })
      .then(function (data) { renderMoodTrendChart(data); })
      .catch(function () { console.warn('情绪趋势数据加载失败'); });

    // 3. 咨询会话柱状图
    fetch(API_BASE + '/analytics/consultation-stats?days=14')
      .then(function (res) { return res.json(); })
      .then(function (data) { renderConsultationChart(data); })
      .catch(function () { console.warn('咨询统计数据加载失败'); });

    // 4. 用户活跃度趋势
    fetch(API_BASE + '/analytics/user-activity?days=14')
      .then(function (res) { return res.json(); })
      .then(function (data) { renderUserActivityChart(data); })
      .catch(function () { console.warn('用户活跃度数据加载失败'); });
  }

  /**
   * 情绪趋势 — 双轴折线图（左: 平均评分 / 右: 记录数量）
   */
  function renderMoodTrendChart(data) {
    var ctx = document.getElementById('chartMoodTrend');
    if (!ctx) return;
    if (typeof Chart === 'undefined') { renderNativeMoodTrendChart(ctx, data); return; }

    var labels = data.map(function (d) { return shortDate(d.date); });
    var scores = data.map(function (d) { return d.avg_score; });
    var counts = data.map(function (d) { return d.count; });

    var canvasCtx = ctx.getContext('2d');

    // 平均评分 — 绿色渐变填充
    var gradientGreen = canvasCtx.createLinearGradient(0, 0, 0, 280);
    gradientGreen.addColorStop(0, 'rgba(91,154,139,0.25)');
    gradientGreen.addColorStop(1, 'rgba(91,154,139,0.0)');

    // 记录数量 — 橙色渐变填充
    var gradientOrange = canvasCtx.createLinearGradient(0, 0, 0, 280);
    gradientOrange.addColorStop(0, 'rgba(249,115,22,0.15)');
    gradientOrange.addColorStop(1, 'rgba(249,115,22,0.0)');

    var chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: '平均情绪评分',
            data: scores,
            borderColor: '#5B9A8B',
            backgroundColor: gradientGreen,
            borderWidth: 2.5,
            fill: true,
            tension: 0.4,
            pointRadius: 4,
            pointBackgroundColor: '#5B9A8B',
            pointBorderColor: '#FFF',
            pointBorderWidth: 2,
            pointHoverRadius: 6,
            spanGaps: false,
            yAxisID: 'y',
            order: 1,
          },
          {
            label: '记录数量',
            data: counts,
            borderColor: '#F97316',
            backgroundColor: gradientOrange,
            borderWidth: 2,
            borderDash: [5, 3],
            fill: true,
            tension: 0.4,
            pointRadius: 3,
            pointBackgroundColor: '#F97316',
            pointBorderColor: '#FFF',
            pointBorderWidth: 2,
            pointHoverRadius: 5,
            spanGaps: false,
            yAxisID: 'y1',
            order: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false,
        },
        plugins: {
          legend: {
            display: true,
            position: 'bottom',
            labels: {
              usePointStyle: true,
              pointStyleWidth: 8,
              padding: 20,
              font: { size: 12 },
              color: '#64748B',
            },
          },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                if (ctx.datasetIndex === 0) {
                  if (ctx.parsed.y === null) return '暂无评分数据';
                  return '平均评分: ' + ctx.parsed.y + ' / 10';
                }
                return '记录数量: ' + ctx.parsed.y + ' 条';
              },
            },
          },
        },
        scales: {
          x: {
            grid: { color: '#F1F5F9', drawBorder: false },
            ticks: { color: '#94A3B8', font: { size: 11 } },
          },
          y: {
            type: 'linear',
            position: 'left',
            min: 1,
            max: 10,
            ticks: {
              stepSize: 1,
              color: '#5B9A8B',
              font: { size: 11 },
              callback: function (v) { return v + ' 分'; },
            },
            grid: { color: '#F1F5F9', drawBorder: false },
            title: {
              display: true,
              text: '平均情绪评分',
              color: '#5B9A8B',
              font: { size: 11 },
            },
          },
          y1: {
            type: 'linear',
            position: 'right',
            beginAtZero: true,
            ticks: {
              stepSize: 1,
              color: '#F97316',
              font: { size: 11 },
              callback: function (v) { return v === Math.floor(v) ? v + ' 条' : ''; },
            },
            grid: { drawOnChartArea: false },
            title: {
              display: true,
              text: '记录数量',
              color: '#F97316',
              font: { size: 11 },
            },
          },
        },
      },
    });
    chartInstances.push(chart);
  }

  /**
   * 咨询会话 — 分组柱状图（会话数 + 参与用户数）
   */
  function renderConsultationChart(data) {
    var ctx = document.getElementById('chartConsultation');
    if (!ctx) return;
    if (typeof Chart === 'undefined') { renderNativeConsultationChart(ctx, data); return; }

    var labels = data.map(function (d) { return shortDate(d.date); });
    var counts = data.map(function (d) { return d.count; });
    var userCounts = data.map(function (d) { return d.user_count; });

    // 会话数量 — 蓝色渐变
    var canvasCtx = ctx.getContext('2d');
    var gradientBlue = canvasCtx.createLinearGradient(0, 0, 0, 280);
    gradientBlue.addColorStop(0, 'rgba(59,130,246,0.75)');
    gradientBlue.addColorStop(1, 'rgba(147,197,253,0.5)');

    // 参与用户数 — 绿色渐变
    var gradientGreen = canvasCtx.createLinearGradient(0, 0, 0, 280);
    gradientGreen.addColorStop(0, 'rgba(16,185,129,0.75)');
    gradientGreen.addColorStop(1, 'rgba(110,231,183,0.5)');

    var chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: '会话数量',
            data: counts,
            backgroundColor: gradientBlue,
            borderColor: '#3B82F6',
            borderWidth: 1,
            borderRadius: { topLeft: 6, topRight: 6 },
            borderSkipped: false,
            order: 1,
          },
          {
            label: '参与用户数',
            data: userCounts,
            backgroundColor: gradientGreen,
            borderColor: '#10B981',
            borderWidth: 1,
            borderRadius: { topLeft: 6, topRight: 6 },
            borderSkipped: false,
            order: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        categoryPercentage: 0.55,
        barPercentage: 1.0,
        plugins: {
          legend: {
            display: true,
            position: 'bottom',
            labels: {
              usePointStyle: true,
              pointStyleWidth: 8,
              padding: 20,
              font: { size: 12 },
              color: '#64748B',
            },
          },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return ctx.dataset.label + ': ' + ctx.parsed.y;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: '#94A3B8', font: { size: 11 } },
          },
          y: {
            beginAtZero: true,
            ticks: {
              stepSize: 1,
              color: '#94A3B8',
              font: { size: 11 },
              callback: function (v) { return v === Math.floor(v) ? v : ''; },
            },
            grid: { color: '#F1F5F9', drawBorder: false },
          },
        },
      },
    });
    chartInstances.push(chart);
  }

  /**
   * 用户活跃度趋势 — 四折线图
   */
  function renderUserActivityChart(data) {
    var ctx = document.getElementById('chartUserActivity');
    if (!ctx) return;
    if (typeof Chart === 'undefined') { renderNativeUserActivityChart(ctx, data); return; }

    var labels = data.map(function (d) { return shortDate(d.date); });
    var activeUsers = data.map(function (d) { return d.active_users; });
    var newUsers = data.map(function (d) { return d.new_users; });
    var diaryUsers = data.map(function (d) { return d.diary_users; });
    var consultationUsers = data.map(function (d) { return d.consultation_users; });

    // 四色配色: 绿 / 紫 / 粉 / 蓝
    var colors = ['#5B9A8B', '#8B5CF6', '#EC4899', '#3B82F6'];
    var fills = [
      'rgba(91,154,139,0.08)',
      'rgba(139,92,246,0.06)',
      'rgba(236,72,153,0.06)',
      'rgba(59,130,246,0.06)',
    ];

    var datasets = [
      { label: '活跃用户', data: activeUsers, color: colors[0], fill: fills[0] },
      { label: '新增用户', data: newUsers, color: colors[1], fill: fills[1], dash: [6, 3] },
      { label: '日记用户', data: diaryUsers, color: colors[2], fill: fills[2], dash: [3, 3] },
      { label: '咨询用户', data: consultationUsers, color: colors[3], fill: fills[3], dash: [2, 4] },
    ];

    var chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: datasets.map(function (ds) {
          return {
            label: ds.label,
            data: ds.data,
            borderColor: ds.color,
            backgroundColor: ds.fill,
            borderWidth: 2,
            borderDash: ds.dash || undefined,
            fill: true,
            tension: 0.4,
            pointRadius: 0,
            pointHoverRadius: 5,
            pointBackgroundColor: ds.color,
            pointBorderColor: '#FFF',
            pointBorderWidth: 2,
          };
        }),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false,
        },
        plugins: {
          legend: {
            display: true,
            position: 'bottom',
            labels: {
              usePointStyle: true,
              pointStyleWidth: 8,
              padding: 20,
              font: { size: 12 },
              color: '#64748B',
            },
          },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                return ctx.dataset.label + ': ' + ctx.parsed.y + ' 人';
              },
            },
          },
        },
        scales: {
          x: {
            grid: { color: '#F1F5F9', drawBorder: false },
            ticks: { color: '#94A3B8', font: { size: 11 } },
          },
          y: {
            beginAtZero: true,
            max: Math.max.apply(null, [1].concat(
              activeUsers, newUsers, diaryUsers, consultationUsers
            ).filter(function (v) { return v != null; })) + 1,
            ticks: {
              stepSize: 1,
              color: '#94A3B8',
              font: { size: 11 },
              callback: function (v) { return v === Math.floor(v) ? v + ' 人' : ''; },
            },
            grid: { color: '#F1F5F9', drawBorder: false },
          },
        },
      },
    });
    chartInstances.push(chart);
  }

  function renderNativeMoodTrendChart(canvas, data) {
    var labels = data.map(function (d) { return shortDate(d.date); });
    renderNativeChart(canvas, {
      type: 'line',
      labels: labels,
      minY: 0,
      maxY: 10,
      datasets: [
        { label: '平均情绪评分', data: data.map(function (d) { return d.avg_score || 0; }), color: '#5E9F94', fill: 'rgba(94,159,148,0.13)' },
        { label: '记录数量', data: data.map(function (d) { return d.count || 0; }), color: '#E7B65F', dashed: true },
      ],
    });
  }

  function renderNativeConsultationChart(canvas, data) {
    renderNativeChart(canvas, {
      type: 'bar',
      labels: data.map(function (d) { return shortDate(d.date); }),
      datasets: [
        { label: '会话数量', data: data.map(function (d) { return d.count || 0; }), color: '#8E7CC3' },
        { label: '参与用户数', data: data.map(function (d) { return d.user_count || 0; }), color: '#5E9F94' },
      ],
    });
  }

  function renderNativeUserActivityChart(canvas, data) {
    renderNativeChart(canvas, {
      type: 'line',
      labels: data.map(function (d) { return shortDate(d.date); }),
      datasets: [
        { label: '活跃用户', data: data.map(function (d) { return d.active_users || 0; }), color: '#5E9F94', fill: 'rgba(94,159,148,0.09)' },
        { label: '新增用户', data: data.map(function (d) { return d.new_users || 0; }), color: '#8E7CC3', dashed: true },
        { label: '日记用户', data: data.map(function (d) { return d.diary_users || 0; }), color: '#E98AA5', dashed: true },
        { label: '咨询用户', data: data.map(function (d) { return d.consultation_users || 0; }), color: '#3B82F6', dashed: true },
      ],
    });
  }

  function renderNativeChart(canvas, options) {
    var resize = function () { drawNativeChart(canvas, options); };
    resize();
    window.addEventListener('resize', resize);
    chartInstances.push({ destroy: function () { window.removeEventListener('resize', resize); } });
  }

  function drawNativeChart(canvas, options) {
    var wrapper = canvas.parentElement;
    var rect = wrapper.getBoundingClientRect();
    var ratio = window.devicePixelRatio || 1;
    var width = Math.max(320, Math.floor(rect.width));
    var height = Math.max(220, Math.floor(rect.height));
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';

    var ctx = canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);

    var pad = { top: 18, right: 24, bottom: 52, left: 42 };
    var chartW = width - pad.left - pad.right;
    var chartH = height - pad.top - pad.bottom;
    var labels = options.labels || [];
    var allValues = [];
    options.datasets.forEach(function (ds) {
      allValues = allValues.concat(ds.data.filter(function (v) { return v !== null && v !== undefined; }));
    });
    var maxY = options.maxY != null ? options.maxY : Math.max.apply(null, [1].concat(allValues));
    var minY = options.minY != null ? options.minY : 0;
    if (maxY === minY) maxY = minY + 1;

    function xAt(i) {
      if (labels.length <= 1) return pad.left + chartW / 2;
      return pad.left + (chartW * i) / (labels.length - 1);
    }
    function yAt(v) {
      return pad.top + chartH - ((v - minY) / (maxY - minY)) * chartH;
    }

    ctx.lineWidth = 1;
    ctx.strokeStyle = '#ECE8DE';
    ctx.fillStyle = '#8A969A';
    ctx.font = '11px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (var g = 0; g <= 4; g++) {
      var y = pad.top + (chartH * g) / 4;
      var value = maxY - ((maxY - minY) * g) / 4;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(width - pad.right, y);
      ctx.stroke();
      ctx.fillText(Math.round(value * 10) / 10, pad.left - 8, y);
    }

    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    labels.forEach(function (label, i) {
      if (labels.length > 8 && i % 2 === 1) return;
      ctx.fillText(label, xAt(i), height - pad.bottom + 16);
    });

    if (options.type === 'bar') {
      drawNativeBars(ctx, options, labels, pad, chartW, chartH, yAt, maxY);
    } else {
      drawNativeLines(ctx, options, labels, pad, chartW, chartH, xAt, yAt, height);
    }
    drawNativeLegend(ctx, options.datasets, pad.left, height - 18);
  }

  function drawNativeLines(ctx, options, labels, pad, chartW, chartH, xAt, yAt, height) {
    options.datasets.forEach(function (ds) {
      var points = ds.data.map(function (v, i) { return { x: xAt(i), y: yAt(v || 0), value: v || 0 }; });
      if (ds.fill && points.length) {
        ctx.beginPath();
        ctx.moveTo(points[0].x, pad.top + chartH);
        points.forEach(function (p) { ctx.lineTo(p.x, p.y); });
        ctx.lineTo(points[points.length - 1].x, pad.top + chartH);
        ctx.closePath();
        ctx.fillStyle = ds.fill;
        ctx.fill();
      }
      ctx.beginPath();
      points.forEach(function (p, i) { i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y); });
      ctx.strokeStyle = ds.color;
      ctx.lineWidth = 2.5;
      ctx.setLineDash(ds.dashed ? [6, 4] : []);
      ctx.stroke();
      ctx.setLineDash([]);
      points.forEach(function (p) {
        ctx.beginPath();
        ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = '#FFFFFF';
        ctx.fill();
        ctx.strokeStyle = ds.color;
        ctx.lineWidth = 2;
        ctx.stroke();
      });
    });
  }

  function drawNativeBars(ctx, options, labels, pad, chartW, chartH, yAt, maxY) {
    var groupW = chartW / Math.max(1, labels.length);
    var barW = Math.min(22, (groupW - 12) / options.datasets.length);
    options.datasets.forEach(function (ds, dsIndex) {
      ds.data.forEach(function (value, i) {
        var x = pad.left + i * groupW + groupW / 2 - (barW * options.datasets.length) / 2 + dsIndex * barW;
        var y = yAt(value || 0);
        var h = pad.top + chartH - y;
        ctx.fillStyle = ds.color;
        roundRect(ctx, x, y, barW - 2, h, 6);
        ctx.fill();
      });
    });
  }

  function drawNativeLegend(ctx, datasets, x, y) {
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.font = '12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif';
    datasets.forEach(function (ds) {
      ctx.fillStyle = ds.color;
      roundRect(ctx, x, y - 5, 10, 10, 3);
      ctx.fill();
      ctx.fillStyle = '#718086';
      ctx.fillText(ds.label, x + 16, y);
      x += ctx.measureText(ds.label).width + 42;
    });
  }

  function roundRect(ctx, x, y, w, h, r) {
    var radius = Math.min(r, Math.abs(w) / 2, Math.abs(h) / 2);
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.arcTo(x + w, y, x + w, y + h, radius);
    ctx.arcTo(x + w, y + h, x, y + h, radius);
    ctx.arcTo(x, y + h, x, y, radius);
    ctx.arcTo(x, y, x + w, y, radius);
    ctx.closePath();
  }

  function ensureInfoModal() {
    var existing = document.getElementById('infoModal');
    if (existing) return existing;
    var modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'infoModal';
    modal.style.display = 'none';
    modal.innerHTML =
      '<div class="modal modal-lg">' +
        '<div class="modal-header">' +
          '<h2 class="modal-title" id="infoModalTitle"></h2>' +
          '<button class="modal-close" id="infoModalClose">&times;</button>' +
        '</div>' +
        '<div class="modal-body" id="infoModalBody"></div>' +
      '</div>';
    document.body.appendChild(modal);
    modal.addEventListener('click', function (e) { if (e.target === modal) hideInfoModal(); });
    document.getElementById('infoModalClose').addEventListener('click', hideInfoModal);
    return modal;
  }

  function showInfoModal(title, bodyHtml) {
    var modal = ensureInfoModal();
    document.getElementById('infoModalTitle').innerHTML = title;
    document.getElementById('infoModalBody').innerHTML = bodyHtml;
    modal.style.display = 'flex';
  }

  function hideInfoModal() {
    var modal = document.getElementById('infoModal');
    if (modal) modal.style.display = 'none';
  }

  function renderPage(page) {
    var config = pageConfig[page] || { title: page, render: renderPlaceholder };
    pageTitle.textContent = config.title;
    content.innerHTML = config.render(config);
    if (typeof config.onReady === 'function') {
      config.onReady();
    }
  }

  function navigateToPage(page) {
    var target = document.querySelector('.nav-item[data-page="' + page + '"]');
    if (target) {
      navItems.forEach(function (n) { n.classList.remove('active'); });
      target.classList.add('active');
      destroyCharts();
      renderPage(page);
    }
  }

  // ====== 侧边栏导航切换 ======
  navItems.forEach(function (item) {
    item.addEventListener('click', function () {
      var page = this.getAttribute('data-page');
      if (!page) return;

      // 切换 active
      navItems.forEach(function (n) { n.classList.remove('active'); });
      this.classList.add('active');

      // 销毁旧图表
      destroyCharts();

      renderPage(page);
    });
  });

  var initialActive = document.querySelector('.nav-item.active');
  renderPage(initialActive ? initialActive.getAttribute('data-page') : 'analytics');

})();

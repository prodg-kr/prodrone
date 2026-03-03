---
title: "일본화약, 드론 낙하산 PARASAFE, ArduPilot 연동으로 안전성 강화"
date: 2025-03-31T12:45:03+09:00
slug: "parasafe-ardupilot-20250331"
description: "일본화약의 드론용 긴급 낙하산 시스템 'PARASAFE'가 ArduPilot 탑재 플라이트 컨트롤러와 연동된다. Pixhawk, CubePilot 등과 호환되며 자동 및 수동 전개가 가능해 산업용 드론의 안전성을 강화한다."
featured_image: "/images/pronews_1772529648_cfbe00e4.jpg"
draft: false
---

<div style="background:#f8f9fa;padding:20px;border-radius:8px;border-left:5px solid #0056b3;margin-bottom:30px;">
<h3 style="margin-top:0;color:#0056b3;">💡 핵심 요약</h3>
<ul><li>일본화약의 드론 낙하산 시스템 'PARASAFE'가 ArduPilot과 연동된다.</li><li>Pixhawk, CubePilot 등 ArduPilot 지원 플라이트 컨트롤러와 호환된다.</li><li>자동 및 수동 트리거를 통한 낙하산 전개가 가능하다.</li><li>산업용 드론의 안전성 향상에 기여할 것으로 기대된다.</li></ul>
</div>

<div class="entry-content rbct clearfix is-highlight-shares" itemprop="articleBody"><div class="ruby-table-contents rbtoc table-fw"><div class="toc-header"><i class="rbi rbi-read"></i><span class="h3">목차</span></div><div class="inner"><a class="table-link anchor-link h5" data-index="rb-heading-index-0" href="#parasafe%e3%81%a8ardupilot%e6%90%ad%e8%bc%89%e3%83%95%e3%83%a9%e3%82%a4%e3%83%88%e3%82%b3%e3%83%b3%e3%83%88%e3%83%ad%e3%83%bc%e3%83%a9%e3%83%bc%e3%81%a8%e3%81%ae%e9%80%a3%e6%90%ba%e3%81%ab%e3%81%a4">PARASAFE와 ArduPilot 탑재 플라이트 컨트롤러 연동</a><a class="table-link-depth anchor-link h5 depth-1" data-index="rb-heading-index-1" href="#%e9%80%a3%e6%90%ba%e3%81%ae%e6%a6%82%e8%a6%81">연동 개요</a><a class="table-link-depth anchor-link h5 depth-1" data-index="rb-heading-index-2" href="#%e9%80%a3%e6%90%ba%e3%81%ae%e7%89%b9%e5%be%b4">연동 특징</a><a class="table-link-depth anchor-link h5 depth-1" data-index="rb-heading-index-3" href="#%e4%bd%9c%e5%8b%95%e6%96%b9%e6%b3%95">작동 방법</a><a class="table-link anchor-link h5" data-index="rb-heading-index-4" href="#ardupilot-developers-conference-2024%e3%81%a7%e3%81%ae%e3%83%87%e3%83%a2%e3%83%b3%e3%82%b9%e3%83%88%e3%83%ac%e3%83%bc%e3%82%b7%e3%83%a7%e3%83%b3">ArduPilot Developers Conference 2024 시연</a><a class="table-link anchor-link h5" data-index="rb-heading-index-5" href="#%e3%83%89%e3%83%ad%e3%83%bc%e3%83%b3%e7%94%a8%e5%ae%89%e5%85%a8%e8%a3%85%e7%bd%aeparasafe">드론용 안전 장치 'PARASAFE'</a></div></div>
<h2 class="rb-heading-index-0" id="parasafe%e3%81%a8ardupilot%e6%90%ad%e8%bc%89%e3%83%95%e3%83%a9%e3%82%a4%e3%83%88%e3%82%b3%e3%83%b3%e3%83%88%e3%83%ad%e3%83%bc%e3%83%a9%e3%83%bc%e3%81%a8%e3%81%ae%e9%80%a3%e6%90%ba%e3%81%ab%e3%81%a4">PARASAFE와 ArduPilot 탑재 플라이트 컨트롤러 연동</h2>
<h3 class="rb-heading-index-1" id="%e9%80%a3%e6%90%ba%e3%81%ae%e6%a6%82%e8%a6%81">연동 개요</h3>
<p>일본화약이 개발한 드론용 긴급 낙하산 시스템 'PARASAFE'가 오픈 소스 비행 제어 소프트웨어인 ArduPilot과 연동된다. 이번 연동은 산업용 드론의 안전성을 한층 강화하는 중요한 계기가 될 것으로 기대된다. ArduPilot은 Pixhawk, CubePilot 등 다양한 플라이트 컨트롤러에서 널리 사용되고 있어, 이번 호환성 확보로 더 많은 드론 운용자와 기업이 PARASAFE를 쉽게 도입하고 활용할 수 있게 되었다. 이는 곧 산업용 드론 운용 환경 전반의 안전 수준 향상으로 이어질 전망이다.</p>
<h3 class="rb-heading-index-2" id="%e9%80%a3%e6%90%ba%e3%81%ae%e7%89%b9%e5%be%b4">연동 특징</h3>
<ul>
<li><span class="b">원활한 통합 및 간편한 설정</span>
<ul>
<li>ArduPilot 환경에서 제공되는 Parachute 명령어를 활용하여 드론 운용 상황에 최적화된 PARASAFE 작동 설정을 간편하게 할 수 있다.</li>
<li>Pixhawk, CubePilot 등 ArduPilot을 지원하는 주요 플라이트 컨트롤러뿐만 아니라, Mission Planner, QGroundControl과 같은 지상 관제국에서도 PARASAFE 기능을 원활하게 사용할 수 있다.</li>
</ul>
</li>
<li><span class="b">자동 및 수동 전개 모두 지원</span>
<ul>
<li><span class="b">자동 트리거:</span> 플라이트 컨트롤러가 드론의 자세 각도나 하강 속도에서 이상을 감지하면, 모든 프로펠러를 즉시 정지시키고 낙하산에 PWM 신호를 출력한다. PARASAFE는 이 신호를 받아 즉시 낙하산을 사출하고 펼쳐 안전한 착륙을 유도한다.</li>
<li><span class="b">수동 트리거:</span> 조종기 스위치나 지상 관제국 명령을 통해 낙하산 작동을 수동으로 제어할 수 있다. 긴급 상황 발생 시 조종자나 관제관이 즉각적으로 스위치를 조작하면, 플라이트 컨트롤러가 프로펠러를 멈추고 낙하산에 신호를 전달하여 신속하게 낙하산을 전개한다.</li>
</ul>
</li>
</ul>
<h3 class="rb-heading-index-3" id="%e4%bd%9c%e5%8b%95%e6%96%b9%e6%b3%95">작동 방법</h3>
<p>드론 조종기(송신기)에 할당된 스위치를 조작하면, ArduPilot을 지원하는 플라이트 컨트롤러(Pixhawk 시리즈, CubePilot 등)는 낙하산 장치로 PWM 신호를 전송한다. 이 신호를 수신한 PARASAFE 낙하산 장치는 즉시 작동하여 안전하게 낙하산을 전개시킨다.</p>
<h2 class="rb-heading-index-4" id="ardupilot-developers-conference-2024%e3%81%a7%e3%81%ae%e3%83%87%e3%83%a2%e3%83%b3%e3%82%b9%e3%83%88%e3%83%ac%e3%83%bc%e3%82%b7%e3%83%a7%e3%83%b3">ArduPilot Developers Conference 2024 시연</h2>
<p>지난 2024년 10월 25일부터 27일까지 일본 이시카와현 가가시에서 개최된 'ArduPilot Developers Conference 2024'에서 PARASAFE와 ArduPilot의 연동 시연이 성공적으로 진행되었다. 시연에서는 CubePilot을 탑재한 Aero Systems West사의 ILM Quadcopter에 PARASAFE를 장착하여 수동 트리거 방식으로 낙하산을 작동시켰다. 시연 결과, 낙하산 전개 후 드론 기체에 어떠한 손상도 발생하지 않아 시스템의 안정성과 신뢰성을 입증했다. 이번 행사에 참여한 전 세계 드론 개발자 및 엔지니어들은 PARASAFE와 ArduPilot의 연동 기술에 높은 관심을 보였다.</p>
<h2 class="rb-heading-index-5" id="%e3%83%89%e3%83%ad%e3%83%bc%e3%83%b3%e7%94%a8%e5%ae%89%e5%85%a8%e8%a3%85%e7%bd%aeparasafe">드론용 안전 장치 'PARASAFE'</h2>
<p>일본화약의 'PARASAFE'는 산업용 드론 추락 시 발생하는 위험을 최소화하기 위해 개발된 긴급 낙하산 시스템이다. 드론 추락 상황이 감지되면 화공품을 작동시켜 즉시 낙하산을 전개하며, 이를 통해 드론을 안전하게 하강시킨다. 일본화약은 자동차 안전 부품(에어백용 인플레이터, 시트벨트용 가스 발생 장치 등) 개발 및 제조 경험을 바탕으로 축적된 화공품 기술을 PARASAFE 개발에 응용하여 높은 안전성과 신뢰성을 확보했다.</p>
<figure>
<img alt="250331_PARASAFE_01" class="alignnone size-full wp-image-114921" decoding="async" fetchpriority="high" height="720" sizes="(max-width: 1200px) 100vw, 1200px" src="https://d2llikhal5te33.cloudfront.net/wpdronenews/wp-content/uploads/2025/03/250331_PARASAFE_01.jpg" srcset="https://d2llikhal5te33.cloudfront.net/wpdronenews/wp-content/uploads/2025/03/250331_PARASAFE_01.jpg 1200w, https://d2llikhal5te33.cloudfront.net/wpdronenews/wp-content/uploads/2025/03/250331_PARASAFE_01-768x461.jpg 768w, https://d2llikhal5te33.cloudfront.net/wpdronenews/wp-content/uploads/2025/03/250331_PARASAFE_01-860x516.jpg 860w" width="1200"/>
<figcaption>PS CA12-01</figcaption>
</figure>
<p>현재 일본화약은 최대 이륙 중량 25kg까지의 산업용 드론에 대응하는 'PS CA12-01' 모델을 출시하여 시장에 공급하고 있다.</p>
<p class="aligncenter">
<a class="btn button" href="https://drone.jp/tag/日本化薬" rel="noopener" target="">▶︎일본화약</a></p>
</div>

---
**원문:** [日本化薬が開発するドローンパラシュートがArduPilot連携。安全性が向上、自動・手動展開に対応](https://drone.jp/news/20250331124503114920.html)

import { NextRequest, NextResponse } from "next/server";
import { ADMIN_SESSION_COOKIE, isValidSession } from "../../../lib/auth";

export const runtime = "nodejs";
export const maxDuration = 60;

type FeedItem = { title:string; url:string; source:string; publisher?:string; publish_time?:string|null; keyword?:string; task?:string };
const MODEL = "gemini-2.5-flash";

export async function POST(req: NextRequest) {
  try {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) return NextResponse.json({ error: "GEMINI_API_KEY 尚未設定" }, { status: 503 });

    const session = req.cookies.get(ADMIN_SESSION_COOKIE)?.value;
    if (!(await isValidSession(session))) return NextResponse.json({ error: "登入已逾時，請重新登入" }, { status: 401 });

    const body = await req.json();
    const periodDays = Math.min(Math.max(Number(body?.periodDays || 7), 1), 30);
    const allItems: FeedItem[] = Array.isArray(body?.items) ? body.items : [];
    const items = allItems.slice(0, 180).map((item, index) => ({
      evidence_id:`E${String(index + 1).padStart(3,"0")}`,
      title:item.title,
      source:item.source,
      publisher:item.publisher||item.source,
      publish_time:item.publish_time||null,
      keyword:item.keyword||"",
      url:item.url,
      task:item.task||""
    }));
    if (!items.length) return NextResponse.json({ error: "指定期間沒有可供分析的資料" }, { status: 400 });

    const prompt = `你是國立臺北教育大學（NTUE）的校級媒體與公開輿情分析助理。請依下列資料產生正式、保守、可供行政主管閱讀的繁體中文輿情報告。\n\n重要原則：\n1. 只能依提供的資料判斷，不得杜撰新聞、留言、人物身分、事件細節或數字。\n2. 搜尋結果標題可能不等於完整文章內容，因此沒有足夠證據時要寫「資料不足」或「尚無法判定」。\n3. 不得把單一貼文或少量留言誇大為大規模輿論。\n4. 負面／風險判斷必須區分：校務風險、媒體追蹤風險、社群擴散風險、聲譽風險。\n5. 對 Dcard、PTT、Threads、Instagram 的內容視為公開社群訊號，不推測發文者真實身分。\n6. 請將內容聚合成「議題」，不要只逐篇摘要。\n7. 所有 evidence_ids 必須只使用輸入資料提供的 evidence_id，不得自創。\n8. 每個 topics、risk_matrix、recommended_actions、notable_items 都要盡可能列出直接支持該判斷的 evidence_ids；若沒有直接依據可以留空陣列。每項建議優先引用 1-5 筆最具代表性的資料，不要無差別塞滿全部來源。\n9. 回傳純 JSON，完全符合 schema。\n\n監測期間：最近 ${periodDays} 天\n輸入資料共 ${items.length} 筆：\n${JSON.stringify(items)}`;

    const evidenceIds = {type:"array",items:{type:"string"},maxItems:8};
    const schema:any = {
      type:"object",
      properties:{
        executive_title:{type:"string"},
        signal:{type:"string",enum:["綠燈","黃燈","橙燈","紅燈"]},
        overall_risk:{type:"string",enum:["低","中低","中","中高","高"]},
        immediate_action:{type:"boolean"},
        immediate_action_reason:{type:"string"},
        confidence_note:{type:"string"},
        top_points:{type:"array",items:{type:"string"},minItems:3,maxItems:5},
        summary:{type:"string"},
        topics:{type:"array",minItems:1,maxItems:8,items:{type:"object",properties:{
          topic:{type:"string"},trend:{type:"string",enum:["上升","持平","下降","新出現","無法判定"]},sentiment:{type:"string",enum:["正面","中性","負面","混合","無法判定"]},volume:{type:"integer"},explanation:{type:"string"},sources:{type:"array",items:{type:"string"},maxItems:8},evidence_ids:evidenceIds
        },required:["topic","trend","sentiment","volume","explanation","sources","evidence_ids"]}},
        sentiment_counts:{type:"object",properties:{positive:{type:"integer"},neutral:{type:"integer"},negative:{type:"integer"},uncertain:{type:"integer"}},required:["positive","neutral","negative","uncertain"]},
        risk_matrix:{type:"array",minItems:4,maxItems:4,items:{type:"object",properties:{category:{type:"string"},level:{type:"string",enum:["低","中低","中","中高","高"]},reason:{type:"string"},evidence_ids:evidenceIds},required:["category","level","reason","evidence_ids"]}},
        recommended_actions:{type:"array",minItems:2,maxItems:6,items:{type:"object",properties:{unit:{type:"string"},action:{type:"string"},priority:{type:"string",enum:["例行","留意","優先","立即"]},evidence_ids:evidenceIds},required:["unit","action","priority","evidence_ids"]}},
        notable_items:{type:"array",minItems:0,maxItems:8,items:{type:"object",properties:{title:{type:"string"},source:{type:"string"},reason:{type:"string"},evidence_ids:evidenceIds},required:["title","source","reason","evidence_ids"]}},
        conclusion:{type:"string"}
      },
      required:["executive_title","signal","overall_risk","immediate_action","immediate_action_reason","confidence_note","top_points","summary","topics","sentiment_counts","risk_matrix","recommended_actions","notable_items","conclusion"]
    };

    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`, {
      method:"POST",
      headers:{"Content-Type":"application/json","x-goog-api-key":apiKey},
      body:JSON.stringify({contents:[{role:"user",parts:[{text:prompt}]}],generationConfig:{responseMimeType:"application/json",responseJsonSchema:schema,temperature:0.2,thinkingConfig:{thinkingBudget:1024}}})
    });
    if (!response.ok) {
      const detail = await response.text();
      console.error("Gemini API error",response.status,detail.slice(0,1000));
      return NextResponse.json({ error:`Gemini API 呼叫失敗（${response.status}）` }, { status:502 });
    }
    const data = await response.json();
    const text = data?.candidates?.[0]?.content?.parts?.map((p:any)=>p?.text||"").join("")||"";
    if (!text) return NextResponse.json({ error:"Gemini 未回傳可用分析" }, { status:502 });
    let report;
    try { report=JSON.parse(text); } catch { return NextResponse.json({ error:"Gemini 回傳格式異常" }, { status:502 }); }
    return NextResponse.json({report,meta:{model:MODEL,analyzed_items:items.length,period_days:periodDays,generated_at:new Date().toISOString()}});
  } catch (error:any) {
    console.error("AI report route failed",error);
    return NextResponse.json({ error:error?.message||"產生報告失敗" }, { status:500 });
  }
}

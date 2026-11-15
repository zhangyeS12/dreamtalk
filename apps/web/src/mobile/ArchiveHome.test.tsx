import {StrictMode} from "react";
import {afterEach,beforeEach,expect,test,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import type {CharacterPack,CoreClient,LibraryCardItem,WorldSettings} from "@dreamtalk/api-client";
import {MobileArchiveHome} from "./ArchiveHome";
vi.mock("../world/cards/CardDesigner",()=>({CardDesigner:({onClose}:{onClose:()=>void})=><div role="dialog" aria-label="合成设计器"><button onClick={onClose}>关闭合成设计器</button></div>}));
const originalPointer=window.PointerEvent;
const world={world_id:"synthetic-world",name:"合成书本",world_time:"43200000000",time_scale:"1",clock_state:"paused",runtime_state:"ready"} as WorldSettings;
const card={card_id:"synthetic-card",name:"合成人物",revision:1,world_ids:[],design:null} as unknown as LibraryCardItem;
function setup(overrides={}){
  const client={listProductWorlds:vi.fn(async()=>[world]),listWorldCovers:vi.fn(async()=>[]),cardPacks:vi.fn(async()=>[]),
    libraryCards:vi.fn(async()=>[card]),selectedPlayer:vi.fn(async()=>({player_id:null})),confirmLibraryJoin:vi.fn(),deleteLibraryCard:vi.fn(),createWorld:vi.fn(async()=>world),...overrides} as unknown as CoreClient;
  const enter=vi.fn(),dirty=vi.fn();
  render(<StrictMode><MobileArchiveHome client={client} onEnter={enter} reconnect={vi.fn()} onDirtyRoot={dirty}/></StrictMode>);
  return{client,enter,dirty};
}
beforeEach(()=>{
  localStorage.clear();
  Object.defineProperty(window,"PointerEvent",{configurable:true,value:class extends MouseEvent {
    pointerId:number;isPrimary:boolean;
    constructor(type:string,init:PointerEventInit){super(type,init);this.pointerId=init.pointerId??1;this.isPrimary=init.isPrimary??true;}
  }});
  for(const name of ["setPointerCapture","releasePointerCapture","hasPointerCapture"]){Object.defineProperty(HTMLElement.prototype,name,{configurable:true,value:vi.fn(()=>false)});}
  Object.defineProperty(HTMLDialogElement.prototype,"showModal",{configurable:true,value:vi.fn(function(this:HTMLDialogElement){this.open=true;})});
  Object.defineProperty(HTMLDialogElement.prototype,"close",{configurable:true,value:vi.fn(function(this:HTMLDialogElement){this.open=false;})});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();Object.defineProperty(window,"PointerEvent",{configurable:true,value:originalPointer});Reflect.deleteProperty(document,"elementFromPoint");});
async function ready(){await waitFor(()=>expect(screen.getByRole("button",{name:"新卡／导入"}).hasAttribute("disabled")).toBe(false));}
async function allCards(){fireEvent.click(screen.getByRole("button",{name:"全部角色卡"}));await screen.findByRole("group",{name:"角色卡"});}
test("the original book actor stays mounted through extraction, face changes and return",async()=>{
  const{enter}=setup();await ready();
  const actor=screen.getByRole("button",{name:"预览世界："+world.name});
  fireEvent.click(actor);
  expect(screen.queryByRole("dialog")).toBeNull();expect(enter).not.toHaveBeenCalled();
  expect(actor.isConnected).toBe(true);
  const controls=screen.getByRole("group",{name:"世界书操作："+world.name});
  fireEvent.click(within(controls).getByLabelText("切换书本面"));
  fireEvent.click(within(controls).getByRole("button",{name:"背面"}));
  await waitFor(()=>expect(actor.dataset.face).toBe("back"));
  fireEvent.click(screen.getByRole("button",{name:"归位世界书"}));
  expect(actor.isConnected).toBe(true);expect(enter).not.toHaveBeenCalled();
  fireEvent.click(actor);
  await waitFor(()=>expect(screen.getByRole("button",{name:"进入世界"}).hasAttribute("disabled")).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"进入世界"}));
  expect(enter).toHaveBeenCalledWith(world);expect(localStorage.getItem("livingworld.lastWorldId")).toBe(world.world_id);
});
test("the lower half starts with real packs and exposes the complete card library",async()=>{
  setup();await ready();
  expect(screen.getByRole("heading",{name:"角色卡与卡包"})).toBeTruthy();
  expect(screen.getByRole("group",{name:"卡包"})).toBeTruthy();
  expect(screen.queryByRole("group",{name:"角色卡"})).toBeNull();
  await allCards();
  expect(within(screen.getByRole("group",{name:"角色卡"})).getByRole("button",{name:"查看角色卡："+card.name})).toBeTruthy();
});
test("the original card remains in its ring during rotation, return and join preview",async()=>{
  const{client,dirty}=setup();await ready();await allCards();
  const actor=within(screen.getByRole("group",{name:"角色卡"})).getByRole("button",{name:"查看角色卡："+card.name});
  fireEvent.click(actor);
  expect(screen.queryByRole("dialog")).toBeNull();expect(actor.isConnected).toBe(true);
  fireEvent.click(screen.getByRole("button",{name:"背面"}));
  await waitFor(()=>expect(actor.dataset.face).toBe("back"));
  fireEvent.click(screen.getByRole("button",{name:"归位角色卡"}));
  expect(actor.isConnected).toBe(true);
  fireEvent.click(actor);
  fireEvent.click(screen.getByRole("button",{name:"加入世界"}));
  expect(screen.getByRole("dialog",{name:/将.*合成人物.*加入世界/})).toBeTruthy();
  expect(client.confirmLibraryJoin).not.toHaveBeenCalled();expect(dirty).toHaveBeenLastCalledWith(true);
  expect(document.querySelector("[data-pack-collection]")?.getAttribute("data-pack-mode")).toBe("cards");
});
test("the archive sky uses the compatible last-world identity and that world's actual time",async()=>{
  localStorage.setItem("livingworld.lastWorldId",world.world_id);
  setup();await ready();
  await waitFor(()=>expect(document.querySelector(".mobile-archive-room [data-kind='sun']")).toBeTruthy());
});
test("unknown world creation reuses its original id instead of making another world",async()=>{
  const create=vi.fn().mockRejectedValueOnce(new Error("synthetic")).mockResolvedValueOnce(world);
  setup({createWorld:create});await ready();
  fireEvent.click(screen.getByRole("button",{name:"新世界"}));
  fireEvent.change(screen.getByRole("textbox",{name:"新世界名称"}),{target:{value:"新合成世界"}});
  fireEvent.click(screen.getByRole("button",{name:"创建世界"}));
  await screen.findByRole("button",{name:"核对并重试创建"});
  fireEvent.click(screen.getByRole("button",{name:"核对并重试创建"}));
  await waitFor(()=>expect(create).toHaveBeenCalledTimes(2));
  expect(create.mock.calls[1]).toEqual(create.mock.calls[0]);
});
test("unavailable card metadata remains recoverable without invented library entries",async()=>{
  setup({libraryCards:vi.fn(async()=>{throw new Error("synthetic");})});await ready();
  expect(screen.getByRole("alert")).toBeTruthy();expect(screen.queryByRole("button",{name:card.name})).toBeNull();
});


test.each([false,true])("the first pack saves, reopens and retains its identity with existing cards=%s",async(hasCards)=>{
  let stored:CharacterPack[]=[];
  const save=vi.fn(async(pack:CharacterPack)=>{const value={...pack,revision:1};stored=[value];return value;});
  const discard=vi.fn(async()=>({discarded:true}));
  setup({libraryCards:vi.fn(async()=>hasCards?[card]:[]),cardPacks:vi.fn(async()=>stored),saveCardPack:save,discardPackDraft:discard});
  await ready();
  fireEvent.click(within(screen.getByRole("group",{name:"卡包"})).getByRole("button",{name:"创建新卡包"}));
  fireEvent.change(screen.getByRole("textbox",{name:"卡包名称"}),{target:{value:"首次合成卡包"}});
  fireEvent.click(screen.getByRole("button",{name:"保存卡包"}));
  await waitFor(()=>expect(screen.queryByRole("textbox",{name:"卡包名称"})).toBeNull());
  expect(save).toHaveBeenCalledTimes(1);expect(save.mock.calls[0][0].revision).toBe(0);
  expect(stored[0].name).toBe("首次合成卡包");expect(stored[0].cardIds).toEqual([]);
  expect(document.querySelector("[data-pack-collection]")?.getAttribute("data-pack-mode")).toBe("selected");
  fireEvent.click(screen.getByRole("button",{name:"设计与装卡"}));
  expect((screen.getByRole("textbox",{name:"卡包名称"}) as HTMLInputElement).value).toBe("首次合成卡包");
  expect(discard).toHaveBeenCalledWith(stored[0].id);
});


test("a real captured pointer tap opens once and designer return keeps the same card actor",async()=>{
  setup();await ready();await allCards();
  const ring=screen.getByRole("group",{name:"角色卡"}),actor=within(ring).getByRole("button",{name:"查看角色卡："+card.name});
  fireEvent.pointerDown(actor,{pointerId:61,button:0,clientX:200,clientY:560,isPrimary:true});
  fireEvent.pointerUp(ring,{pointerId:61,clientX:200,clientY:560,isPrimary:true});
  fireEvent.click(ring,{detail:1});
  expect(screen.getByRole("group",{name:"旋转角色卡"})).toBeTruthy();
  expect(actor.dataset.selected).toBe("true");
  fireEvent.click(screen.getByRole("button",{name:"设计卡面"}));
  expect(screen.getByRole("dialog",{name:"合成设计器"})).toBeTruthy();
  fireEvent.click(screen.getByRole("button",{name:"关闭合成设计器"}));
  expect(actor.isConnected).toBe(true);expect(actor.dataset.selected).toBe("true");
  expect(document.querySelector("[data-pack-collection]")?.getAttribute("data-pack-mode")).toBe("cards");
});

test("carrying upward opens the existing join preview with its target and never commits directly",async()=>{
  const{client}=setup();await ready();await allCards();
  const book=screen.getByRole("button",{name:"预览世界："+world.name});
  Object.defineProperty(document,"elementFromPoint",{configurable:true,value:vi.fn(()=>book)});
  const ring=screen.getByRole("group",{name:"角色卡"}),actor=within(ring).getByRole("button",{name:"查看角色卡："+card.name});
  fireEvent.pointerDown(actor,{pointerId:71,button:0,clientX:200,clientY:600,isPrimary:true});
  fireEvent.pointerMove(ring,{pointerId:71,clientX:200,clientY:200,isPrimary:true});
  expect(book.hasAttribute("data-card-drop")).toBe(true);
  fireEvent.pointerUp(ring,{pointerId:71,clientX:200,clientY:200,isPrimary:true});
  const dialog=await screen.findByRole("dialog",{name:/将.*合成人物.*加入世界/});
  expect((within(dialog).getByRole("combobox") as HTMLSelectElement).value).toBe(world.world_id);
  expect(client.confirmLibraryJoin).not.toHaveBeenCalled();
  expect(book.hasAttribute("data-card-drop")).toBe(false);
});

test("horizontal touch on a card browses while vertical touch keeps the carry contract",async()=>{
  setup();await ready();await allCards();
  const ring=screen.getByRole("group",{name:"角色卡"}),actor=within(ring).getByRole("button",{name:"查看角色卡："+card.name});
  fireEvent.pointerDown(actor,{pointerId:81,button:0,clientX:200,clientY:600,isPrimary:true});
  fireEvent.pointerMove(ring,{pointerId:81,clientX:100,clientY:604,isPrimary:true});
  expect(Number(ring.dataset.offset)).toBeGreaterThan(90);
  expect(document.querySelector(".mobile-card-carry-label")).toBeNull();
  fireEvent.pointerUp(ring,{pointerId:81,clientX:100,clientY:604,isPrimary:true});
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.queryByRole("group",{name:"旋转角色卡"})).toBeNull();
});

test("large collections stay bounded even before the first viewport measurement",async()=>{
  const worlds=Array.from({length:500},(_,i)=>({...world,world_id:"synthetic-large-"+i,name:"合成书本"+i}));
  setup({listProductWorlds:vi.fn(async()=>worlds)});await ready();
  await screen.findByRole("button",{name:"预览世界：合成书本0"});
  expect(document.querySelectorAll("[data-book-key]").length).toBeLessThanOrEqual(25);
});

test("a newly confirmed card from the pack browse screen appears in the actual card ring",async()=>{
  const saved={...card,card_id:"synthetic-new",name:"新合成人物"};
  let stored:LibraryCardItem[]=[];
  const preview={preview_id:"synthetic-preview",card_id:saved.card_id,expected_revision:0,reviewed_hash:"synthetic-hash",content:{
    import_id:saved.card_id,replaces_import_id:null,kind:"character",reviewed_hash:"synthetic-hash",characters:[{id:"definition",name:saved.name,description:"",personality:"",background:"",scenario:"",speech_guidance:"",creator_notes:"",tags:[],example_dialogue:[],authored_instructions:{}}],lorebooks:[],entries:[],warnings:[]
  }};
  const confirm=vi.fn(async()=>{stored=[saved];return saved;});
  const include=vi.fn(),discard=vi.fn(async()=>({discarded:true}));
  setup({libraryCards:vi.fn(async()=>stored),previewLibraryEditor:vi.fn(async()=>preview),confirmLibraryCard:confirm,discardLibraryPreview:discard,includeCardInPack:include});
  await ready();expect(screen.queryByRole("group",{name:"角色卡"})).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"新卡／导入"}));
  fireEvent.change(screen.getByLabelText("角色名称"),{target:{value:saved.name}});
  fireEvent.click(screen.getByRole("button",{name:"预览角色设定"}));
  const accept=await screen.findByRole("button",{name:"确认保存到卡库"});
  expect(confirm).not.toHaveBeenCalled();
  fireEvent.click(accept);
  const ring=await screen.findByRole("group",{name:"旋转角色卡"});
  const actor=within(ring).getByRole("button",{name:"查看角色卡："+saved.name});
  expect(actor.dataset.selected).toBe("true");expect(actor.isConnected).toBe(true);
  expect(document.querySelector("[data-pack-collection]")?.getAttribute("data-pack-mode")).toBe("cards");
  expect(confirm).toHaveBeenCalledTimes(1);expect(include).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"归位角色卡"}));expect(actor.isConnected).toBe(true);
});

test.each(["browse","selected","flipped"])("returning from all cards clears transient card UI and remains clean after reentry: %s",async(mode)=>{
  const{client}=setup();await ready();
  for(let cycle=0;cycle<2;cycle++){
    await allCards();
    expect(screen.queryByRole("button",{name:"归位角色卡"})).toBeNull();
    if(mode!=="browse"){
      fireEvent.click(within(screen.getByRole("group",{name:"角色卡"})).getByRole("button",{name:"查看角色卡："+card.name}));
      if(mode==="flipped")fireEvent.click(screen.getByRole("button",{name:"背面"}));
      expect(screen.getByRole("button",{name:"归位角色卡"})).toBeTruthy();
    }
    fireEvent.click(screen.getByRole("button",{name:/^返回卡包/}));
    expect(screen.getByRole("button",{name:"全部角色卡"})).toBeTruthy();
    expect(screen.queryByRole("button",{name:"归位角色卡"})).toBeNull();
    expect(screen.queryByRole("button",{name:"加入世界"})).toBeNull();
    expect(document.querySelector(".mobile-card-dock")).toBeNull();
    expect(document.querySelector(".mobile-archive-lower")?.hasAttribute("data-expanded")).toBe(false);
    expect(document.querySelector(".mobile-card-heading small")?.textContent).toBe("0 个卡包 · 1 张角色卡");
  }
  expect(client.confirmLibraryJoin).not.toHaveBeenCalled();expect(client.deleteLibraryCard).not.toHaveBeenCalled();
});

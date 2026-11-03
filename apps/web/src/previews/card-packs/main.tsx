import { StrictMode, useEffect, useSyncExternalStore, type ComponentProps } from "react";
import { createRoot } from "react-dom/client";
import { WorldArchivePage } from "../../WorldArchivePage";
import { CharacterLibrary } from "../../world/cards/CharacterLibrary";
import { CardPackLibrary } from "../../world/cards/packs/CardPackLibrary";
import { getSnapshot, subscribe, images, previewClient, savePack } from "./previewStore";
import "../../style.css";
import "./preview.css";

function PackCollection(props: ComponentProps<typeof CharacterLibrary>) {
  const state = useSyncExternalStore(subscribe, getSnapshot);
  const { onCountChange } = props;
  useEffect(() => onCountChange(state.cards.length), [onCountChange, state.cards.length]);
  return <CardPackLibrary packs={state.packs} cards={state.cards} images={images} active={props.active} onSave={savePack} onEditingChange={props.onEditingChange}
    renderCards={pack => <CharacterLibrary {...props} client={previewClient(pack?.id)} onCountChange={() => props.onCountChange(state.cards.length)} />} />;
}
const client = previewClient();
createRoot(document.getElementById("root")!).render(<StrictMode><WorldArchivePage client={client} initialWorldId={null} onEnter={() => window.alert("这是卡包交互预览。可切换回角色卡继续体验拆包；真实世界与聊天请从正式项目进入。")} displayTime={value => value} renderCardCollection={props => <PackCollection {...props} />} /><span className="pack-preview-note">网页预览 · 刷新后复原</span></StrictMode>);
